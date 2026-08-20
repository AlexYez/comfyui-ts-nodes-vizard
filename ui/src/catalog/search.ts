import MiniSearch from "minisearch";

import type { CatalogArticle, LocaleCode } from "../types/contracts";

interface SearchDocument {
  id: string;
  articleId: string;
  locale: string;
  title: string;
  summary: string;
  tags: string;
  concepts: string;
  classType: string;
  aliases: string;
  body: string;
}

export interface CatalogSearchResult {
  article: CatalogArticle;
  score: number;
}

function normaliseTerm(term: string): string {
  return term
    .toLocaleLowerCase()
    .replaceAll("ё", "е")
    // Frequent Russian transliteration variants; both document and query take this path.
    .replaceAll("сэмпл", "семпл")
    .replaceAll("сэмпл", "семпл");
}

function tokenise(text: string): string[] {
  return (text.match(/[\p{L}\p{N}_+.-]+/gu) ?? []).map(normaliseTerm);
}

function stripMarkdown(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)]\([^)]*\)/g, "$1")
    .replace(/[>#*_~|]/g, " ")
    .slice(0, 20_000);
}

export class CatalogSearchIndex {
  readonly #engine: MiniSearch<SearchDocument>;
  readonly #articles = new Map<string, CatalogArticle>();

  constructor(articles: readonly CatalogArticle[]) {
    this.#engine = new MiniSearch<SearchDocument>({
      fields: ["title", "summary", "tags", "concepts", "classType", "aliases", "body"],
      storeFields: ["articleId", "locale"],
      tokenize: tokenise,
      processTerm: normaliseTerm,
      searchOptions: {
        boost: { title: 5, classType: 5, aliases: 4, tags: 3, concepts: 2, summary: 2 },
        prefix: true,
        fuzzy: 0.16
      }
    });

    const documents: SearchDocument[] = articles.map((article, index) => {
      const id = `${article.manifest.articleId}\u0000${article.manifest.locale}\u0000${index}`;
      this.#articles.set(id, article);
      return {
        id,
        articleId: article.manifest.articleId,
        locale: article.manifest.locale,
        title: article.title,
        summary: article.summary,
        tags: article.tags.join(" "),
        concepts: article.concepts.join(" "),
        classType: article.manifest.runtimeIdentity?.classType ?? "",
        aliases: [
          ...(article.manifest.runtimeIdentity?.aliases ?? []),
          ...article.manifest.searchAliases
        ].join(" "),
        body: stripMarkdown(article.body)
      };
    });
    if (documents.length > 0) this.#engine.addAll(documents);
  }

  search(query: string, preferredLocale: LocaleCode, limit = 40): CatalogSearchResult[] {
    const trimmed = query.trim();
    if (!trimmed) return [];
    const results = this.#engine.search(trimmed, {
      combineWith: "AND",
      prefix: true,
      fuzzy: trimmed.length >= 5 ? 0.16 : false
    });

    return results
      .map((result) => {
        const article = this.#articles.get(String(result.id));
        if (!article) return null;
        const localeBoost = article.manifest.locale === preferredLocale ? 1.25 : 1;
        const queryTerm = normaliseTerm(trimmed);
        const exactNames = [
          article.title,
          article.manifest.runtimeIdentity?.classType ?? "",
          ...(article.manifest.runtimeIdentity?.aliases ?? []),
          ...article.manifest.searchAliases
        ].map(normaliseTerm);
        // A deliberately authored exact name or alias must outrank incidental
        // body/tag matches from the much larger full catalog.
        const samplerFamilyBoost = queryTerm === "семплер"
          && (article.manifest.runtimeIdentity?.classType ?? "").startsWith("KSampler")
          ? 80
          : 0;
        const exactNameBoost = exactNames.includes(queryTerm)
          ? 100
          : exactNames.some((name) => tokenise(name).includes(queryTerm))
            ? 50
            : 0;
        return { article, score: (result.score + exactNameBoost + samplerFamilyBoost) * localeBoost };
      })
      .filter((item): item is CatalogSearchResult => item !== null)
      .sort((left, right) => right.score - left.score)
      .slice(0, limit);
  }
}

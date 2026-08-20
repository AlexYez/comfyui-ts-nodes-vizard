import { createMissingArticle } from "../runtime/missingArticle";
import {
  sameNodeProvenance,
  serialiseNodeKey
} from "../runtime/nodeKey";
import type {
  CatalogArticle,
  CatalogDiagnostics,
  CatalogDocument,
  LocaleCode,
  NodeKey,
  ResolvedArticle,
  RuntimeNodeDefinition
} from "../types/contracts";
import { CatalogSearchIndex, type CatalogSearchResult } from "./search";

const localeFallbacks = (preferred: LocaleCode): string[] => [
  preferred,
  preferred.split("-")[0] ?? preferred,
  "ru",
  "en"
];

function selectLocale(
  candidates: readonly CatalogArticle[],
  preferredLocale: LocaleCode
): CatalogArticle | undefined {
  for (const locale of localeFallbacks(preferredLocale)) {
    const match = candidates.find((article) => article.manifest.locale === locale);
    if (match) return match;
  }
  return candidates[0];
}

function uniqueIdentityCount(articles: readonly CatalogArticle[]): number {
  return new Set(
    articles.flatMap((article) => {
      const identity = article.manifest.runtimeIdentity;
      return identity ? [serialiseNodeKey(identity)] : [];
    })
  ).size;
}

export class CatalogRegistry {
  readonly catalog: CatalogDocument;
  readonly diagnostics: CatalogDiagnostics;
  readonly #byArticleId = new Map<string, CatalogArticle[]>();
  readonly #byNodeKey = new Map<string, CatalogArticle[]>();
  readonly #byClassType = new Map<string, CatalogArticle[]>();
  readonly #byAlias = new Map<string, CatalogArticle[]>();
  readonly #runtime = new Map<string, RuntimeNodeDefinition>();
  readonly #search: CatalogSearchIndex;

  constructor(
    catalog: CatalogDocument,
    runtime: ReadonlyMap<string, RuntimeNodeDefinition> = new Map()
  ) {
    this.catalog = catalog;
    this.diagnostics = {
      duplicateArticleIds: [],
      duplicateRuntimeIdentities: [],
      aliasConflicts: [],
      ambiguousClassTypes: []
    };

    for (const article of catalog.articles) {
      const idCandidates = this.#byArticleId.get(article.manifest.articleId) ?? [];
      if (idCandidates.some((item) => item.manifest.locale === article.manifest.locale)) {
        this.diagnostics.duplicateArticleIds.push(
          `${article.manifest.articleId}:${article.manifest.locale}`
        );
        continue;
      }
      idCandidates.push(article);
      this.#byArticleId.set(article.manifest.articleId, idCandidates);

      const identity = article.manifest.runtimeIdentity;
      if (!identity) continue;
      const nodeKey = serialiseNodeKey(identity);
      const exactCandidates = this.#byNodeKey.get(nodeKey) ?? [];
      if (
        exactCandidates.some((item) => item.manifest.locale === article.manifest.locale)
      ) {
        this.diagnostics.duplicateRuntimeIdentities.push(
          `${nodeKey}:${article.manifest.locale}`
        );
        continue;
      }
      exactCandidates.push(article);
      this.#byNodeKey.set(nodeKey, exactCandidates);

      const classCandidates = this.#byClassType.get(identity.classType) ?? [];
      classCandidates.push(article);
      this.#byClassType.set(identity.classType, classCandidates);

      for (const alias of identity.aliases) {
        const aliasCandidates = this.#byAlias.get(alias) ?? [];
        aliasCandidates.push(article);
        this.#byAlias.set(alias, aliasCandidates);
      }
    }

    for (const [classType, candidates] of this.#byClassType) {
      if (uniqueIdentityCount(candidates) > 1) {
        this.diagnostics.ambiguousClassTypes.push(classType);
      }
    }
    for (const [alias, candidates] of this.#byAlias) {
      if (this.#byClassType.has(alias) || uniqueIdentityCount(candidates) > 1) {
        this.diagnostics.aliasConflicts.push(alias);
      }
    }

    for (const [classType, definition] of runtime) {
      this.#runtime.set(classType, definition);
    }
    this.#search = new CatalogSearchIndex(this.#searchableArticles(catalog.locale));
  }

  get size(): number {
    return this.catalog.articles.length;
  }

  get runtimeSize(): number {
    return this.#runtime.size;
  }

  runtimeClassTypes(): ReadonlySet<string> {
    return new Set(this.#runtime.keys());
  }

  runtimeDefinition(classType: string): RuntimeNodeDefinition | undefined {
    return this.#runtime.get(classType);
  }

  /** Returns true for one and only one catalog identity, including frontend-only nodes. */
  isUniqueCatalogClassType(classType: string): boolean {
    return uniqueIdentityCount(this.#byClassType.get(classType) ?? []) === 1;
  }

  getByArticleId(
    articleId: string,
    preferredLocale: LocaleCode
  ): CatalogArticle | undefined {
    return selectLocale(this.#byArticleId.get(articleId) ?? [], preferredLocale);
  }

  getByNodeKey(
    key: NodeKey,
    preferredLocale: LocaleCode
  ): CatalogArticle | undefined {
    const exact = selectLocale(this.#byNodeKey.get(serialiseNodeKey(key)) ?? [], preferredLocale);
    if (exact) return exact;

    const candidates = (this.#byClassType.get(key.classType) ?? []).filter((article) => {
      const identity = article.manifest.runtimeIdentity;
      return identity ? sameNodeProvenance(identity, key) : false;
    });
    if (uniqueIdentityCount(candidates) === 1) return selectLocale(candidates, preferredLocale);
    return undefined;
  }

  getByClassType(
    classType: string,
    preferredLocale: LocaleCode
  ): CatalogArticle | undefined {
    const runtime = this.#runtime.get(classType);
    if (runtime) return this.getByNodeKey(runtime, preferredLocale);
    // Without `/object_info`, provenance for server nodes is unknown. A custom
    // package may have replaced the same class_type, so only exact frontend
    // registry entries can be resolved safely.
    const candidates = (this.#byClassType.get(classType) ?? []).filter(
      (article) => article.manifest.runtimeIdentity?.kind === "frontend"
    );
    if (uniqueIdentityCount(candidates) === 1) return selectLocale(candidates, preferredLocale);

    const aliases = (this.#byAlias.get(classType) ?? []).filter(
      (article) => article.manifest.runtimeIdentity?.kind === "frontend"
    );
    return uniqueIdentityCount(aliases) === 1
      ? selectLocale(aliases, preferredLocale)
      : undefined;
  }

  resolveByClassType(
    classType: string,
    preferredLocale: LocaleCode
  ): ResolvedArticle {
    const runtime = this.#runtime.get(classType);
    const article = runtime
      ? this.getByNodeKey(runtime, preferredLocale) ??
        this.#resolveAliasForRuntime(classType, runtime, preferredLocale)
      : this.getByClassType(classType, preferredLocale);

    if (!article) {
      return {
        article: createMissingArticle(classType, runtime, preferredLocale),
        runtime,
        availability: "generated",
        generated: true
      };
    }
    return this.#resolved(article, runtime);
  }

  resolveByArticleId(
    articleId: string,
    preferredLocale: LocaleCode
  ): ResolvedArticle | undefined {
    const article = this.getByArticleId(articleId, preferredLocale);
    if (!article) return undefined;
    const identity = article.manifest.runtimeIdentity;
    if (!identity) return this.#resolved(article, undefined);
    const runtime = this.#runtime.get(identity.classType);
    return this.#resolved(
      article,
      runtime && sameNodeProvenance(identity, runtime) ? runtime : undefined
    );
  }

  list(preferredLocale: LocaleCode): CatalogArticle[] {
    const groups = new Map<string, CatalogArticle[]>();
    for (const article of this.catalog.articles) {
      const identity = article.manifest.runtimeIdentity;
      const key = identity
        ? serialiseNodeKey(identity)
        : `article:${article.manifest.articleId}`;
      const entries = groups.get(key) ?? [];
      entries.push(article);
      groups.set(key, entries);
    }
    return [...groups.values()]
      .map((articles) => selectLocale(articles, preferredLocale))
      .filter((article): article is CatalogArticle => article !== undefined)
      .sort((left, right) => left.title.localeCompare(right.title, preferredLocale));
  }

  search(query: string, locale: LocaleCode, limit = 40): CatalogSearchResult[] {
    return this.#search.search(query, locale, limit);
  }

  withRuntime(runtime: ReadonlyMap<string, RuntimeNodeDefinition>): CatalogRegistry {
    return new CatalogRegistry(this.catalog, runtime);
  }

  #resolveAliasForRuntime(
    alias: string,
    runtime: RuntimeNodeDefinition,
    locale: LocaleCode
  ): CatalogArticle | undefined {
    const candidates = (this.#byAlias.get(alias) ?? []).filter((article) => {
      const identity = article.manifest.runtimeIdentity;
      if (!identity) return false;
      return sameNodeProvenance({ ...identity, classType: alias }, runtime);
    });
    return uniqueIdentityCount(candidates) === 1
      ? selectLocale(candidates, locale)
      : undefined;
  }

  #resolved(
    article: CatalogArticle,
    runtime: RuntimeNodeDefinition | undefined
  ): ResolvedArticle {
    const expectedHash =
      article.manifest.compatibility.schemaFingerprint ??
      article.manifest.editorial.schemaHash;
    const availability = !runtime
      ? article.manifest.runtimeIdentity?.kind === "frontend"
        ? "available"
        : "not-installed"
      : expectedHash && !/^sha256:0{64}$/.test(expectedHash) && expectedHash !== runtime.schemaHash
        ? "schema-changed"
        : "available";
    return { article, runtime, availability, generated: false };
  }

  #searchableArticles(locale: LocaleCode): CatalogArticle[] {
    const articles = [...this.catalog.articles];
    for (const [classType, runtime] of this.#runtime) {
      if (!this.getByNodeKey(runtime, locale)) {
        articles.push(createMissingArticle(classType, runtime, locale));
      }
    }
    return articles;
  }
}

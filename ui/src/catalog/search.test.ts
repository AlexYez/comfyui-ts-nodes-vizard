import catalogText from "../../../content/generated/catalog.json?raw";
import { describe, expect, it } from "vitest";

import { decodeCatalog } from "./schema";
import { CatalogSearchIndex } from "./search";

describe("Russian offline search", () => {
  const catalog = decodeCatalog(JSON.parse(catalogText));
  const index = new CatalogSearchIndex(catalog.articles);

  it.each(["сэмплер", "семплер"])("finds KSampler for %s", (query) => {
    const results = index.search(query, "ru");
    expect(results.slice(0, 2).map((item) => item.article.manifest.articleId)).toContain(
      "core.ksampler"
    );
    expect(results.slice(0, 2).map((item) => item.article.manifest.articleId)).toContain(
      "core.ksampler-advanced"
    );
  });

  it("indexes Cyrillic editorial aliases", () => {
    const article = catalog.articles.find(
      (item) => item.manifest.articleId === "core.checkpoint-loader-simple"
    );
    expect(article?.manifest.searchAliases).toContain("чекпоинт");
    const localIndex = new CatalogSearchIndex(article ? [article] : []);
    expect(localIndex.search("чекпоинт", "ru")[0]?.article.manifest.articleId)
      .toBe("core.checkpoint-loader-simple");
  });

  it("folds ё/e consistently", () => {
    const article = catalog.articles.find((item) => item.manifest.articleId === "core.ksampler");
    if (article) article.manifest.searchAliases.push("всё");
    const localIndex = new CatalogSearchIndex(article ? [article] : []);
    expect(localIndex.search("все", "ru")).toHaveLength(1);
  });
});

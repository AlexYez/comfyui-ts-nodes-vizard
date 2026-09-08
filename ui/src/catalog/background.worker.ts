import { decodeCatalog, parseStoredCatalog } from "./schema";
import { CatalogSearchIndex } from "./search";
import { decodeObjectInfo, parseObjectInfoText } from "../runtime/objectInfo";
import type { CatalogArticle } from "../types/contracts";

let search: CatalogSearchIndex | undefined;
const scope = globalThis as unknown as {
  onmessage: (event: MessageEvent) => void;
  postMessage: (value: unknown) => void;
};
scope.onmessage = async ({ data }) => {
  const { id, operation, payload } = data;
  try {
    let value: unknown;
    switch (operation) {
      case "catalog": value = decodeCatalog(JSON.parse(payload.text), payload.url); break;
      case "stored": value = parseStoredCatalog(payload); break;
      case "runtime": value = await decodeObjectInfo(parseObjectInfoText(payload), false); break;
      case "index": search = new CatalogSearchIndex(payload as CatalogArticle[]); value = true; break;
      case "search":
        if (!search) throw new Error("Search index is not ready");
        value = search.search(payload.query, payload.locale).map(({ article, score }) => ({
          articleId: article.manifest.articleId, locale: article.manifest.locale, score
        }));
        break;
      default: throw new Error("Unknown background operation");
    }
    scope.postMessage({ id, value });
  } catch (error) {
    scope.postMessage({ id, error: error instanceof Error ? error.message : String(error) });
  }
};

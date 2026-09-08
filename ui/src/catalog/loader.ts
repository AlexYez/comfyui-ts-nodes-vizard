import type { CatalogDocument } from "../types/contracts";
import { catalogUrlCandidates } from "./locations";
import { decodeCatalog, parseStoredCatalog } from "./schema";
import type { CatalogStore, StoredCatalogRecord } from "./storage";
import { compareCatalogVersions } from "./version";
import { runBackground } from "./background";

export interface CatalogLoadResult {
  catalog: CatalogDocument;
  source: "bundled" | "signed-cache" | "cache-fallback";
  warnings: string[];
}

export interface CatalogLoaderOptions {
  store: CatalogStore;
  fetch?: typeof globalThis.fetch;
  urls?: string[];
}

export class CatalogLoader {
  readonly #store: CatalogStore;
  readonly #fetch: typeof globalThis.fetch;
  readonly #urls?: string[];

  constructor(options: CatalogLoaderOptions) {
    this.#store = options.store;
    this.#fetch = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.#urls = options.urls;
  }

  async load(signal?: AbortSignal): Promise<CatalogLoadResult> {
    const warnings: string[] = [];
    const cached = await this.#safeGetCached(warnings, signal);
    signal?.throwIfAborted();
    const urls = this.#urls ?? catalogUrlCandidates();
    let bundled: CatalogDocument | null = null;

    for (const url of urls) {
      try {
        const response = await this.#fetch(url, {
          signal,
          headers: { Accept: "application/json" },
          credentials: "same-origin"
        });
        if (!response.ok) {
          warnings.push(`${url}: HTTP ${response.status}`);
          continue;
        }
        bundled = typeof Worker !== "undefined"
          ? await runBackground<CatalogDocument>("catalog", { text: await response.text(), url: response.url || url }, signal)
          : decodeCatalog(await response.json(), response.url || url);
        break;
      } catch (error) {
        signal?.throwIfAborted();
        warnings.push(`${url}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    signal?.throwIfAborted();
    if (!bundled && cached) {
      return { catalog: cached.catalog, source: "cache-fallback", warnings };
    }
    if (!bundled) {
      throw new AggregateError(warnings.map((warning) => new Error(warning)), "Catalog unavailable");
    }

    if (
      cached?.origin === "signed-update" &&
      compareCatalogVersions(cached.catalog.catalogVersion, bundled.catalogVersion) >= 0
    ) {
      return { catalog: cached.catalog, source: "signed-cache", warnings };
    }

    if (
      !cached ||
      cached.catalog.catalogVersion !== bundled.catalogVersion ||
      cached.origin !== "bundled"
    ) {
      await this.#safeCommit(
        {
          catalog: bundled,
          origin: "bundled",
          storedAt: new Date().toISOString()
        },
        warnings
      );
    }
    return { catalog: bundled, source: "bundled", warnings };
  }

  async #safeGetCached(warnings: string[], signal?: AbortSignal): Promise<StoredCatalogRecord | null> {
    try {
      const cached = await this.#store.getActive();
      if (!cached) return null;
      const catalog = typeof Worker !== "undefined"
        ? await runBackground<CatalogDocument | null>("stored", cached.catalog, signal)
        : parseStoredCatalog(cached.catalog);
      if (!catalog) {
        warnings.push("Catalog cache: invalid active snapshot ignored");
        return null;
      }
      if (cached.origin !== "bundled" && cached.origin !== "signed-update") {
        warnings.push("Catalog cache: invalid snapshot origin ignored");
        return null;
      }
      return { ...cached, catalog };
    } catch (error) {
      warnings.push(`Catalog cache: ${error instanceof Error ? error.message : String(error)}`);
      return null;
    }
  }

  async #safeCommit(record: StoredCatalogRecord, warnings: string[]): Promise<void> {
    try {
      await this.#store.commit(record);
    } catch (error) {
      warnings.push(`Catalog cache: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

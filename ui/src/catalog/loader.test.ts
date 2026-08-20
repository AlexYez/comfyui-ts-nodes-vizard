import { describe, expect, it, vi } from "vitest";

import { CatalogLoader } from "./loader";
import { MemoryCatalogStore } from "./storage";

const bundled = {
  schemaVersion: "1.0",
  catalogVersion: "1.0.0",
  locale: "ru",
  generatedAt: "2026-08-13T00:00:00Z",
  articles: [{
    manifest: {
      articleId: "core.valid",
      kind: "core",
      locale: "ru",
      runtimeIdentity: {
        classType: "ValidNode",
        kind: "server",
        origin: "backend",
        aliases: []
      },
      status: "active",
      compatibility: {},
      relations: [],
      searchAliases: []
    },
    title: "Valid",
    summary: "Valid bundled catalog",
    tags: [],
    concepts: [],
    body: "# Valid"
  }]
};

describe("CatalogLoader cached record validation", () => {
  it("ignores a corrupt higher-version cache instead of selecting it", async () => {
    const store = new MemoryCatalogStore();
    await store.commit({
      catalog: {
        schemaVersion: "1.0",
        catalogVersion: "999.0.0",
        locale: "ru",
        generatedAt: "",
        articles: "corrupt"
      },
      origin: "signed-update",
      storedAt: "2026-08-13T00:00:00Z"
    } as never);
    const result = await new CatalogLoader({
      store,
      urls: ["/catalog.json"],
      fetch: vi.fn().mockResolvedValue(new Response(JSON.stringify(bundled), { status: 200 }))
    }).load();
    expect(result.source).toBe("bundled");
    expect(result.catalog.catalogVersion).toBe("1.0.0");
    expect(result.warnings).toContain("Catalog cache: invalid active snapshot ignored");
  });

  it("ignores a structurally valid cache from an unsupported future schema", async () => {
    const store = new MemoryCatalogStore();
    await store.commit({
      catalog: { ...bundled, schemaVersion: "2.0", catalogVersion: "999.0.0" },
      origin: "signed-update",
      storedAt: "2026-08-13T00:00:00Z"
    } as never);
    const result = await new CatalogLoader({
      store,
      urls: ["/catalog.json"],
      fetch: vi.fn().mockResolvedValue(new Response(JSON.stringify(bundled), { status: 200 }))
    }).load();
    expect(result.source).toBe("bundled");
    expect(result.catalog.schemaVersion).toBe("1.0");
    expect(result.warnings).toContain("Catalog cache: invalid active snapshot ignored");
  });
});

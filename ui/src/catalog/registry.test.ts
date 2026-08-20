import { decodeCatalog } from "./schema";
import { describe, expect, it } from "vitest";
import { CatalogRegistry } from "./registry";
import type { RuntimeNodeDefinition } from "../types/contracts";

function article(
  articleId: string,
  classType: string,
  packageId: string,
  pythonModule: string,
  aliases: string[] = []
) {
  return {
    manifest: {
      articleId,
      kind: "core",
      locale: "ru",
      runtimeIdentity: {
        classType,
        packageId,
        pythonModule,
        origin: "backend",
        aliases
      },
      status: "active"
    },
    title: articleId,
    summary: articleId,
    tags: [],
    concepts: [],
    body: `# ${articleId}`
  };
}

function runtime(
  classType: string,
  packageId: string,
  pythonModule: string
): RuntimeNodeDefinition {
  return {
    classType,
    packageId,
    pythonModule,
    kind: "server",
    displayName: classType,
    description: "",
    category: "test",
    deprecated: false,
    experimental: false,
    apiNode: false,
    inputs: [],
    outputs: [],
    schemaHash: `sha256:${"0".repeat(64)}`,
    raw: {}
  };
}

function catalog(articles: unknown[]) {
  return decodeCatalog({
    schemaVersion: "1",
    catalogVersion: "1.0.0",
    locale: "ru",
    generatedAt: "",
    articles
  });
}

describe("exact runtime resolver", () => {
  it("never opens a core article for a third-party class_type override", () => {
    const custom = runtime("CollisionNode", "third-party", "custom_nodes.third-party.nodes");
    const registry = new CatalogRegistry(
      catalog([article("core.collision", "CollisionNode", "comfy-core", "nodes")]),
      new Map([[custom.classType, custom]])
    );
    const resolved = registry.resolveByClassType("CollisionNode", "ru");
    expect(resolved.generated).toBe(true);
    expect(resolved.article.manifest.articleId).toContain("generated:");
  });

  it("resolves the complete package/module/class tuple", () => {
    const core = runtime("ExactNode", "comfy-core", "nodes");
    const registry = new CatalogRegistry(
      catalog([article("core.exact", "ExactNode", "comfy-core", "nodes")]),
      new Map([[core.classType, core]])
    );
    expect(registry.resolveByClassType("ExactNode", "ru").article.manifest.articleId)
      .toBe("core.exact");
  });

  it("rejects ambiguous class types and aliases without provenance", () => {
    const registry = new CatalogRegistry(catalog([
      article("a.one", "Duplicate", "one", "custom_nodes.one", ["Legacy"]),
      article("a.two", "Duplicate", "two", "custom_nodes.two", ["Legacy"])
    ]));
    expect(registry.getByClassType("Duplicate", "ru")).toBeUndefined();
    expect(registry.getByClassType("Legacy", "ru")).toBeUndefined();
    expect(registry.diagnostics.ambiguousClassTypes).toContain("Duplicate");
    expect(registry.diagnostics.aliasConflicts).toContain("Legacy");
  });

  it("does not trust a server classType when object_info provenance is unavailable", () => {
    const registry = new CatalogRegistry(
      catalog([article("core.offline", "OfflineNode", "comfy-core", "nodes")])
    );
    expect(registry.getByClassType("OfflineNode", "ru")).toBeUndefined();
    expect(registry.resolveByClassType("OfflineNode", "ru").generated).toBe(true);
  });
});

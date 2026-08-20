import { decodeCatalog } from "./schema";
import { describe, expect, it } from "vitest";

describe("catalog decoder", () => {
  it("accepts the compiled node/relation contract without losing semantics", () => {
    const catalog = decodeCatalog({
      schemaVersion: "1.0",
      catalogVersion: "1.2.3",
      locale: "ru",
      generatedAt: "2026-08-13T00:00:00Z",
      articles: [{
        manifest: {
          articleId: "core.test",
          kind: "core",
          locale: "ru",
          node: {
            nodeId: "TestNode",
            packageId: "comfy-core",
            pythonModule: "nodes",
            kind: "backend"
          },
          status: "active",
          compatibility: { schemaFingerprint: `sha256:${"a".repeat(64)}` },
          relations: [
            { type: "related", articleId: "core.related" },
            { type: "alternative", articleId: "core.alt" },
            { type: "replacedBy", articleId: "core.new" }
          ],
          searchAliases: ["русский псевдоним"]
        },
        title: "Test",
        summary: "Summary",
        tags: [],
        concepts: [],
        body: "# Test"
      }]
    });
    const manifest = catalog.articles[0]?.manifest;
    expect(manifest?.runtimeIdentity).toMatchObject({
      classType: "TestNode",
      packageId: "comfy-core",
      pythonModule: "nodes",
      kind: "server"
    });
    expect(manifest?.relations).toEqual({
      related: ["core.related"],
      alternatives: ["core.alt"],
      replacedBy: "core.new"
    });
    expect(manifest?.searchAliases).toEqual(["русский псевдоним"]);
    expect(manifest?.compatibility.schemaFingerprint).toBe(`sha256:${"a".repeat(64)}`);
  });
});

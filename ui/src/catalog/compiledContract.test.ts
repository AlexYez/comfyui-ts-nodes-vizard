import catalogText from "../../../content/generated/catalog.json?raw";
import { describe, expect, it } from "vitest";

import { assertCompiledCatalog, compiledCatalogSchemaErrors } from "./compiledContract";

describe("shared compiled catalog contract", () => {
  it("accepts the exact artifact emitted by the Python compiler", () => {
    const catalog: unknown = JSON.parse(catalogText);
    expect(compiledCatalogSchemaErrors(catalog)).toEqual([]);
    expect(() => assertCompiledCatalog(catalog)).not.toThrow();
  });

  it("rejects semantic drift between node and runtime identities", () => {
    const catalog = JSON.parse(catalogText) as {
      articles: Array<{ manifest: { node: { nodeId: string } } }>;
    };
    if (catalog.articles[0]) catalog.articles[0].manifest.node.nodeId = "DifferentNode";
    expect(() => assertCompiledCatalog(catalog)).toThrow(/inconsistent node\/runtime identity/);
  });
});

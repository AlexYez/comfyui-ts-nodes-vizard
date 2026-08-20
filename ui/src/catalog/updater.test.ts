import { getPublicKeyAsync, signAsync } from "@noble/ed25519";
import { describe, expect, it, vi } from "vitest";

import { canonicalJson } from "../runtime/objectInfo";
import { MemoryCatalogStore } from "./storage";
import {
  CatalogUpdater,
  type CatalogUpdaterConfig,
  type SignedUpdateManifest
} from "./updater";

const encoder = new TextEncoder();

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

async function hash(bytes: Uint8Array): Promise<string> {
  const stable = new Uint8Array(bytes.byteLength);
  stable.set(bytes);
  const digest = await crypto.subtle.digest("SHA-256", stable);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

interface FixtureOptions {
  path?: string;
  signedSize?: number;
  servedCatalog?: string;
  publicKeyOverride?: string;
  damageSignature?: boolean;
  maxCatalogBytes?: number;
  installedComfyui?: string;
  comfyuiRange?: string;
  mutateCatalog?: (catalog: Record<string, unknown>) => void;
}

async function fixture(options: FixtureOptions = {}) {
  const catalog = {
    schemaVersion: "1.0",
    catalogVersion: "2.0.0",
    locale: "ru",
    generatedAt: "2026-08-13T12:00:00Z",
    articles: [{
      manifest: {
        articleId: "core.secure",
        kind: "core",
        locale: "ru",
        node: {
          packageId: "comfy-core",
          pythonModule: "nodes",
          nodeId: "SecureNode",
          kind: "backend"
        },
        runtimeIdentity: {
          classType: "SecureNode",
          packageId: "comfy-core",
          pythonModule: "nodes",
          origin: "backend",
          aliases: []
        },
        status: "active",
        experimental: false,
        compatibility: {
          comfyui: ">=0.32.0",
          frontend: ">=1.48.7",
          verifiedOn: "2026-08-13",
          sourceRevision: "ComfyUI v0.32.0",
          schemaFingerprint: `sha256:${"0".repeat(64)}`
        },
        relations: [],
        recipes: [],
        workflows: [],
        editorialState: "approved",
        editorial: {
          state: "approved",
          owner: "Test owner",
          reviewedBy: "Test reviewer",
          reviewedAt: "2026-08-13",
          factsReviewedAt: "2026-08-13",
          schemaHash: `sha256:${"0".repeat(64)}`
        },
        searchAliases: [],
        assets: [],
        sources: [{
          sourceId: "test-source",
          title: "Signed updater fixture",
          url: "https://docs.comfy.org/",
          publisher: "Comfy-Org",
          kind: "documentation",
          accessedAt: "2026-08-13",
          supports: ["test fixture"]
        }]
      },
      title: "Secure",
      summary: "Signed catalog update test fixture.",
      tags: [],
      concepts: [],
      body: "# Secure"
    }]
  };
  options.mutateCatalog?.(catalog);
  const catalogText = JSON.stringify(catalog);
  const catalogBytes = encoder.encode(catalogText);
  const artifactPath = options.path ?? "generated/catalog.json";
  const seed = new Uint8Array(32).fill(7);
  const publicKey = await getPublicKeyAsync(seed);
  const unsigned = {
    $schema: "schemas/update-manifest.schema.v1.json",
    schemaVersion: "1.0" as const,
    catalogVersion: "2.0.0",
    publishedAt: "2026-08-13T12:00:00Z",
    canonicalization: "comfy-nodes-wizard-json-v1" as const,
    signatureScope: "top-level-manifest-excluding-signature" as const,
    compatibility: { comfyui: options.comfyuiRange ?? ">=0.32.0", frontend: ">=1.48.7" },
    inventory: {
      source: "object_info.json",
      comfyuiVersion: "0.32.0",
      frontendVersion: "1.48.7",
      capturedAt: "2026-08-13T12:00:00Z"
    },
    artifacts: [{
      path: artifactPath,
      sha256: await hash(catalogBytes),
      size: options.signedSize ?? catalogBytes.byteLength,
      url: `https://updates.example/${artifactPath}`,
      contentType: "application/json"
    }],
    changes: {
      summary: "A signed test update for the catalog.",
      added: ["core.secure"],
      updated: [],
      deprecated: [],
      removed: []
    }
  };
  const signatureBytes = await signAsync(encoder.encode(canonicalJson(unsigned)), seed);
  let signature = base64url(signatureBytes);
  if (options.damageSignature) signature = `${signature[0] === "A" ? "B" : "A"}${signature.slice(1)}`;
  const manifest: SignedUpdateManifest = {
    ...unsigned,
    signature: {
      algorithm: "Ed25519",
      keyId: "release-1",
      publicKey: base64url(publicKey),
      value: signature
    }
  };
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("manifest.json")) {
      return new Response(JSON.stringify(manifest), { status: 200 });
    }
    return new Response(options.servedCatalog ?? catalogText, { status: 200 });
  });
  const config: CatalogUpdaterConfig = {
    enabled: true,
    manifestUrl: "https://updates.example/manifest.json",
    publicKeys: { "release-1": options.publicKeyOverride ?? base64url(publicKey) },
    installedVersions: {
      comfyui: options.installedComfyui ?? "0.32.0",
      frontend: "1.48.7"
    },
    maxCatalogBytes: options.maxCatalogBytes,
    fetch
  };
  return { config, catalog, manifest };
}

describe("signed catalog updater", () => {
  it("verifies, confirms, persists last-known-good, and rolls back", async () => {
    const { config } = await fixture();
    const store = new MemoryCatalogStore();
    await store.commit({
      catalog: {
        schemaVersion: "1.0",
        catalogVersion: "1.0.0",
        locale: "ru",
        generatedAt: "",
        articles: []
      },
      origin: "bundled",
      storedAt: "2026-08-13T00:00:00Z"
    });
    const updater = new CatalogUpdater(config, store);
    const result = await updater.check("1.0.0");
    expect(result.status).toBe("available");
    if (result.status !== "available") return;
    const confirm = vi.fn().mockResolvedValue(true);
    await updater.apply(result.candidate, confirm);
    expect((await store.getActive())?.catalog.catalogVersion).toBe("2.0.0");
    expect((await updater.rollback())?.catalog.catalogVersion).toBe("1.0.0");
  });

  it("rejects catalog tampering after a valid manifest signature", async () => {
    const { config } = await fixture({ servedCatalog: '{"tampered":true}' });
    await expect(new CatalogUpdater(config, new MemoryCatalogStore()).check("1.0.0"))
      .rejects.toThrow(/size|SHA-256/);
  });

  it("rejects a damaged signature and a wrong trusted key", async () => {
    const damaged = await fixture({ damageSignature: true });
    await expect(new CatalogUpdater(damaged.config, new MemoryCatalogStore()).check("1.0.0"))
      .rejects.toThrow(/signature/);
    const wrong = await fixture({ publicKeyOverride: base64url(new Uint8Array(32).fill(9)) });
    await expect(new CatalogUpdater(wrong.config, new MemoryCatalogStore()).check("1.0.0"))
      .rejects.toThrow(/trusted keyring/);
  });

  it("rejects unsafe paths, oversize artifacts, and incompatible runtimes", async () => {
    const unsafe = await fixture({ path: "../catalog.json" });
    await expect(new CatalogUpdater(unsafe.config, new MemoryCatalogStore()).check("1.0.0"))
      .rejects.toThrow(/Unsafe/);
    const oversize = await fixture({ signedSize: 1000, maxCatalogBytes: 100 });
    await expect(new CatalogUpdater(oversize.config, new MemoryCatalogStore()).check("1.0.0"))
      .rejects.toThrow(/exceeds/);
    const incompatible = await fixture({ installedComfyui: "0.31.0" });
    await expect(new CatalogUpdater(incompatible.config, new MemoryCatalogStore()).check("1.0.0"))
      .rejects.toThrow(/incompatible/);
  });

  it("rejects a signed but structurally malformed catalog", async () => {
    const malformed = await fixture({
      mutateCatalog: (catalog) => {
        const articles = catalog.articles as Array<Record<string, unknown>>;
        (articles[0]?.manifest as Record<string, unknown>).relations = [
          { type: "related", articleId: "missing.article" }
        ];
      }
    });
    await expect(
      new CatalogUpdater(malformed.config, new MemoryCatalogStore()).check("1.0.0")
    ).rejects.toThrow(/unknown article/);
  });

  it("enforces the shared compiled schema before tolerant decoding", async () => {
    const wrongOrigin = await fixture({
      mutateCatalog: (catalog) => {
        const articles = catalog.articles as Array<Record<string, unknown>>;
        const manifest = articles[0]?.manifest as Record<string, unknown>;
        (manifest.runtimeIdentity as Record<string, unknown>).origin = "server";
      }
    });
    await expect(
      new CatalogUpdater(wrongOrigin.config, new MemoryCatalogStore()).check("1.0.0")
    ).rejects.toThrow(/compiled schema/);

    const unknownField = await fixture({
      mutateCatalog: (catalog) => {
        const articles = catalog.articles as Array<Record<string, unknown>>;
        const manifest = articles[0]?.manifest as Record<string, unknown>;
        manifest.executablePayload = "not part of the data contract";
      }
    });
    await expect(
      new CatalogUpdater(unknownField.config, new MemoryCatalogStore()).check("1.0.0")
    ).rejects.toThrow(/additional property/);
  });

  it("supports explicit comma ranges and rejects ambiguous shorthand", async () => {
    const bounded = await fixture({ comfyuiRange: ">=0.32.0,<0.33.0" });
    await expect(
      new CatalogUpdater(bounded.config, new MemoryCatalogStore()).check("1.0.0")
    ).resolves.toMatchObject({ status: "available" });
    const shorthand = await fixture({ comfyuiRange: "^0.32.0" });
    await expect(
      new CatalogUpdater(shorthand.config, new MemoryCatalogStore()).check("1.0.0")
    ).rejects.toThrow(/Unsupported compatibility range/);
  });

  it("passes an abort signal to injectable fetch and enforces a finite timeout", async () => {
    const { config } = await fixture();
    let signal: AbortSignal | undefined;
    config.timeoutMs = 10;
    config.fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(signal?.reason), { once: true });
      });
    });
    await expect(new CatalogUpdater(config, new MemoryCatalogStore()).check("1.0.0"))
      .rejects.toMatchObject({ name: "TimeoutError" });
    expect(signal?.aborted).toBe(true);
  });
});

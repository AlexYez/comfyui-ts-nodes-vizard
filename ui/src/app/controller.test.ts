import { describe, expect, it, vi } from "vitest";

import { ComfyBridge } from "../bridge/ComfyBridge";
import { MemoryCatalogStore } from "../catalog/storage";
import { decodeCatalog } from "../catalog/schema";
import { DailyUpdateSchedule, UpdatePreference } from "../catalog/updateSchedule";
import type { ComfyAppLike } from "../types/comfy";
import type { RuntimeNodeDefinition } from "../types/contracts";
import { WizardController } from "./controller";
import {
  boundedChanges,
  signedCatalogSize,
  updateConfirmationMessage
} from "./controller";
import type { CatalogUpdateCandidate } from "../catalog/updater";

function runtime(classType: string): RuntimeNodeDefinition {
  return {
    classType,
    packageId: "comfy-core",
    pythonModule: "nodes",
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

describe("Wizard navigation history", () => {
  it("bounds update change presentation while keeping signed totals and artifact size", () => {
    const added = Array.from({ length: 20 }, (_, index) => `core.added-${index}`);
    const candidate = {
      catalog: { catalogVersion: "2.0.0" },
      manifest: {
        changes: {
          summary: "Summary",
          added,
          updated: ["core.updated"],
          deprecated: [],
          removed: ["core.removed"]
        },
        artifacts: [{ path: "generated/catalog.json", size: 4096 }]
      }
    } as unknown as CatalogUpdateCandidate;
    expect(signedCatalogSize(candidate)).toBe(4096);
    expect(boundedChanges(candidate).added).toEqual({ total: 20, items: added.slice(0, 12) });
    expect(updateConfirmationMessage(candidate, false)).toContain("Added (20)");
    expect(updateConfirmationMessage(candidate, false)).toContain("(+14)");
    expect(updateConfirmationMessage(candidate, false)).toContain("4096 bytes");
  });
  it("navigates known → generated → back → forward without losing the generated card", async () => {
    const bridge = new ComfyBridge({ registerExtension: vi.fn() } as ComfyAppLike);
    vi.spyOn(bridge, "fetchObjectInfo").mockResolvedValue(new Map([
      ["KnownNode", runtime("KnownNode")],
      ["UnknownNode", runtime("UnknownNode")]
    ]));
    const bundled = {
      schemaVersion: "1.0",
      catalogVersion: "1.0.0",
      locale: "ru",
      generatedAt: "",
      articles: [{
        manifest: {
          articleId: "core.known",
          kind: "core",
          locale: "ru",
          runtimeIdentity: {
            classType: "KnownNode",
            packageId: "comfy-core",
            pythonModule: "nodes",
            origin: "backend",
            aliases: []
          },
          status: "active",
          relations: []
        },
        title: "Known",
        summary: "Known node",
        tags: [],
        concepts: [],
        body: "# Known"
      }]
    };
    const controller = new WizardController({
      bridge,
      locale: "ru",
      store: new MemoryCatalogStore(),
      catalogUrls: ["/catalog.json"],
      fetch: vi.fn().mockResolvedValue(new Response(JSON.stringify(bundled), {
        status: 200,
        headers: { "content-type": "application/json" }
      }))
    });
    await controller.initialise();
    controller.selectClassType("UnknownNode");
    expect(controller.getSnapshot().selected?.generated).toBe(true);
    controller.goBack();
    expect(controller.getSnapshot().selected?.article.manifest.articleId).toBe("core.known");
    controller.goForward();
    expect(controller.getSnapshot().selected?.generated).toBe(true);
    expect(controller.getSnapshot().selected?.article.manifest.runtimeIdentity?.classType)
      .toBe("UnknownNode");
  });

  it("rolls back only to a validated previous snapshot after confirmation", async () => {
    const catalogJson = (version: string, articleId: string) => ({
      schemaVersion: "1.0",
      catalogVersion: version,
      locale: "ru",
      generatedAt: "",
      articles: [{
        manifest: {
          articleId,
          kind: "core",
          locale: "ru",
          runtimeIdentity: {
            classType: "KnownNode",
            packageId: "comfy-core",
            pythonModule: "nodes",
            origin: "backend",
            aliases: []
          },
          status: "active",
          relations: []
        },
        title: articleId,
        summary: articleId,
        tags: [],
        concepts: [],
        body: `# ${articleId}`
      }]
    });
    const previousJson = catalogJson("1.0.0", "core.previous");
    const currentJson = catalogJson("2.0.0", "core.current");
    const store = new MemoryCatalogStore();
    await store.commit({
      catalog: decodeCatalog(previousJson),
      origin: "bundled",
      storedAt: "2026-08-12T00:00:00Z"
    });
    await store.commit({
      catalog: decodeCatalog(currentJson),
      origin: "signed-update",
      storedAt: "2026-08-13T00:00:00Z"
    });
    const bridge = new ComfyBridge({ registerExtension: vi.fn() } as ComfyAppLike);
    vi.spyOn(bridge, "fetchObjectInfo").mockResolvedValue(new Map([["KnownNode", runtime("KnownNode")]]));
    vi.spyOn(bridge, "fetchSystemVersions").mockResolvedValue({ backend: "0.32.0", frontend: "1.48.7" });
    const confirm = vi.spyOn(bridge, "confirm").mockResolvedValue(true);
    const controller = new WizardController({
      bridge,
      locale: "ru",
      store,
      catalogUrls: ["/catalog.json"],
      fetch: vi.fn().mockResolvedValue(new Response(JSON.stringify(currentJson), { status: 200 }))
    });
    await controller.initialise();
    expect(controller.getSnapshot().canRollback).toBe(true);
    await controller.rollbackCatalog();
    expect(confirm).toHaveBeenCalledWith("Откатить каталог?", expect.stringContaining("1.0.0"));
    expect(controller.getSnapshot().registry?.catalog.catalogVersion).toBe("1.0.0");
    expect(controller.getSnapshot().selected?.article.manifest.articleId).toBe("core.previous");
    expect((await store.getActive())?.catalog.catalogVersion).toBe("1.0.0");
  });

  it("blocks scheduled and manual network checks when the persistent toggle is off", async () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); }
    };
    const preference = new UpdatePreference(storage);
    preference.setEnabled(false);
    const schedule = new DailyUpdateSchedule(storage);
    const updateFetch = vi.fn();
    const bridge = new ComfyBridge({ registerExtension: vi.fn() } as ComfyAppLike);
    vi.spyOn(bridge, "fetchObjectInfo").mockResolvedValue(new Map([["KnownNode", runtime("KnownNode")]]));
    vi.spyOn(bridge, "fetchSystemVersions").mockResolvedValue({ backend: "0.32.0", frontend: "1.48.7" });
    const catalogJson = {
      schemaVersion: "1.0",
      catalogVersion: "1.0.0",
      locale: "ru",
      generatedAt: "",
      articles: [{
        manifest: {
          articleId: "core.known",
          kind: "core",
          locale: "ru",
          runtimeIdentity: { classType: "KnownNode", origin: "backend", aliases: [] },
          status: "active",
          relations: []
        },
        title: "Known",
        summary: "Known",
        tags: [],
        concepts: [],
        body: "# Known"
      }]
    };
    const controller = new WizardController({
      bridge,
      locale: "ru",
      store: new MemoryCatalogStore(),
      catalogUrls: ["/catalog.json"],
      fetch: vi.fn().mockResolvedValue(new Response(JSON.stringify(catalogJson), { status: 200 })),
      updatePreference: preference,
      updateSchedule: schedule,
      updateConfig: {
        enabled: true,
        manifestUrl: "https://updates.example/manifest.json",
        publicKeys: { release: "trusted-key" },
        installedVersions: { comfyui: "0.32.0", frontend: "1.48.7" },
        fetch: updateFetch
      }
    });
    await controller.initialise();
    await controller.checkForUpdates();
    expect(controller.getSnapshot().updatesEnabled).toBe(false);
    expect(controller.getSnapshot().updateConfigured).toBe(true);
    expect(updateFetch).not.toHaveBeenCalled();
  });

  it("aborts an in-flight check and preserves disabled state when updates are switched off", async () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); }
    };
    const preference = new UpdatePreference(storage);
    const schedule = new DailyUpdateSchedule(storage);
    schedule.markChecked();
    let seenSignal: AbortSignal | undefined;
    let resolveFetch: ((value: Response) => void) | undefined;
    const updateFetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      seenSignal = init?.signal ?? undefined;
      return new Promise<Response>((resolve) => { resolveFetch = resolve; });
    });
    const bridge = new ComfyBridge({ registerExtension: vi.fn() } as ComfyAppLike);
    vi.spyOn(bridge, "fetchObjectInfo").mockResolvedValue(new Map([["KnownNode", runtime("KnownNode")]]));
    vi.spyOn(bridge, "fetchSystemVersions").mockResolvedValue({ backend: "0.32.0", frontend: "1.48.7" });
    const catalogJson = {
      schemaVersion: "1.0",
      catalogVersion: "1.0.0",
      locale: "ru",
      generatedAt: "",
      articles: [{
        manifest: {
          articleId: "core.known",
          kind: "core",
          locale: "ru",
          runtimeIdentity: { classType: "KnownNode", origin: "backend", aliases: [] },
          status: "active",
          relations: []
        },
        title: "Known",
        summary: "Known",
        tags: [],
        concepts: [],
        body: "# Known"
      }]
    };
    const controller = new WizardController({
      bridge,
      locale: "ru",
      store: new MemoryCatalogStore(),
      catalogUrls: ["/catalog.json"],
      fetch: vi.fn().mockResolvedValue(new Response(JSON.stringify(catalogJson), { status: 200 })),
      updatePreference: preference,
      updateSchedule: schedule,
      updateConfig: {
        enabled: true,
        manifestUrl: "https://updates.example/manifest.json",
        publicKeys: { release: "trusted-key" },
        installedVersions: { comfyui: "0.32.0", frontend: "1.48.7" },
        fetch: updateFetch,
        timeoutMs: 60_000
      }
    });
    await controller.initialise();
    const pending = controller.checkForUpdates();
    await vi.waitFor(() => expect(updateFetch).toHaveBeenCalledOnce());
    controller.setUpdatesEnabled(false);
    expect(seenSignal?.aborted).toBe(true);
    resolveFetch?.(new Response("{}", { status: 500 }));
    await pending;
    expect(controller.getSnapshot().update).toEqual({
      status: "disabled",
      detail: "Network update checks are disabled by the user."
    });
    expect(controller.getSnapshot().updatesEnabled).toBe(false);
  });
});

import { ComfyBridge } from "../bridge/ComfyBridge";
import { describe, expect, it, vi } from "vitest";
import type { ComfyAppLike } from "../types/comfy";
import {
  decodeArticleArtifacts,
  openWorkflowArtifact,
  type ArticleArtifact
} from "./adapters";

const artifact: ArticleArtifact = {
  id: "workflow.test",
  kind: "workflow",
  title: "Test",
  payload: { nodes: [], links: [] }
};

describe("workflow adapter", () => {
  it("emits no workflow action for a fragment-only recipe", () => {
    const decoded = decodeArticleArtifacts(
      [{
        recipeId: "recipe.fragment-only",
        title: "Fragment only",
        workflow: null,
        fragmentData: {
          fragmentId: "fragment.only",
          title: "Fragment only",
          nodes: [{ ref: "node", classType: "ExampleNode" }],
          connections: []
        }
      }],
      undefined
    );

    expect(decoded.some((item) => item.kind === "fragment")).toBe(true);
    expect(decoded.some((item) => item.kind === "workflow")).toBe(false);
  });

  it("keeps a declared recipe workflow available when it is embedded in the recipe", () => {
    const decoded = decodeArticleArtifacts(
      [{
        recipeId: "recipe.with-workflow",
        title: "Recipe with workflow",
        workflow: { id: "workflow.declared" },
        workflowData: { nodes: [{ id: 1, type: "ExampleNode" }], links: [], version: 0.4 }
      }],
      undefined
    );

    expect(decoded.find((item) => item.kind === "workflow")).toMatchObject({
      id: "workflow.declared",
      title: "Recipe with workflow",
      payload: { version: 0.4 }
    });
  });

  it("keeps the declared workflow id and recipe title for compiled workflow data", () => {
    const decoded = decodeArticleArtifacts(
      [{
        recipeId: "recipe.test",
        title: "Проверочный рецепт",
        workflow: { id: "workflow.test" }
      }],
      [{
        nodes: [],
        links: [],
        extra: { nodes_wizard: { recipeId: "recipe.test" } }
      }]
    );
    expect(decoded.find((item) => item.kind === "workflow")).toMatchObject({
      id: "workflow.test",
      title: "Проверочный рецепт"
    });
  });

  it("opens a new temporary workflow through the official workflow store", async () => {
    const temporary = { id: "temporary" };
    const createNewTemporary = vi.fn().mockResolvedValue(temporary);
    const openWorkflow = vi.fn().mockResolvedValue(undefined);
    const loadGraphData = vi.fn();
    const app = {
      registerExtension: vi.fn(),
      loadGraphData,
      extensionManager: { workflow: { createNewTemporary, openWorkflow } }
    } as unknown as ComfyAppLike;
    const bridge = new ComfyBridge(app);
    vi.spyOn(bridge, "confirm").mockResolvedValue(true);

    await expect(openWorkflowArtifact(artifact, bridge, "en")).resolves.toBe("loaded");
    expect(createNewTemporary).toHaveBeenCalledWith(undefined, artifact.payload);
    expect(openWorkflow).toHaveBeenCalledWith(temporary);
    expect(loadGraphData).not.toHaveBeenCalled();
  });

  it("downloads when the workflow store is unavailable and never overwrites the graph", async () => {
    const loadGraphData = vi.fn();
    const bridge = new ComfyBridge({
      registerExtension: vi.fn(),
      loadGraphData
    } as unknown as ComfyAppLike);
    vi.spyOn(bridge, "confirm").mockResolvedValue(true);
    const createObjectURL = vi.fn().mockReturnValue("blob:test");
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await expect(openWorkflowArtifact(artifact, bridge, "en")).resolves.toBe("downloaded");
    expect(createObjectURL).toHaveBeenCalled();
    expect(loadGraphData).not.toHaveBeenCalled();
  });
});

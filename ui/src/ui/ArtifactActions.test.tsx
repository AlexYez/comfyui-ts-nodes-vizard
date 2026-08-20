import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WizardController } from "../app/controller";
import type { CatalogArticle } from "../types/contracts";
import { ArtifactActions } from "./ArtifactActions";

describe("ArtifactActions", () => {
  it("shows the fragment but no full-workflow action for a fragment-only recipe", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true
    });
    const openTemporaryWorkflow = vi.fn();
    const toast = vi.fn();
    const controller = {
      getSnapshot: () => ({ locale: "en" }),
      bridge: { openTemporaryWorkflow, toast }
    } as unknown as WizardController;
    const article = {
      manifest: {
        articleId: "core.fragment-only",
        kind: "core",
        locale: "ru",
        searchAliases: [],
        status: "draft",
        compatibility: {},
        relations: { related: [], alternatives: [] },
        assets: [],
        editorial: {},
        sources: []
      },
      title: "Fragment-only article",
      summary: "A fragment-only test article.",
      tags: [],
      concepts: [],
      body: "Test",
      recipeData: [{
        recipeId: "recipe.fragment-only",
        title: "Fragment-only recipe",
        fragmentData: {
          fragmentId: "fragment.only",
          title: "Fragment only",
          nodes: [{ ref: "node", classType: "ExampleNode" }],
          connections: []
        }
      }]
    } satisfies CatalogArticle;

    render(<ArtifactActions article={article} controller={controller} />);

    expect(screen.getByRole("button", { name: /Copy fragment JSON/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Open workflow/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Copy fragment JSON/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(openTemporaryWorkflow).not.toHaveBeenCalled();
  });
});

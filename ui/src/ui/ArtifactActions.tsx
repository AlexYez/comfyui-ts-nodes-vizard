import { useMemo } from "react";

import type { WizardController } from "../app/controller";
import {
  copyArtifact,
  decodeArticleArtifacts,
  openWorkflowArtifact
} from "../artifacts/adapters";
import type { CatalogArticle } from "../types/contracts";

export function ArtifactActions({
  article,
  controller
}: {
  article: CatalogArticle;
  controller: WizardController;
}) {
  const artifacts = useMemo(
    () => decodeArticleArtifacts(article.recipeData, article.workflowData),
    [article.recipeData, article.workflowData]
  );
  if (artifacts.length === 0) return null;
  const ru = controller.getSnapshot().locale === "ru";

  return (
    <section className="nw-actions" aria-label={ru ? "Готовые материалы" : "Ready-to-use assets"}>
      {artifacts.map((artifact) => (
        <button
          className="nw-button"
          key={`${artifact.kind}:${artifact.id}`}
          onClick={() => {
            if (artifact.kind === "workflow") {
              void openWorkflowArtifact(artifact, controller.bridge, controller.getSnapshot().locale)
                .then((result) => {
                  if (result === "loaded") controller.bridge.toast("success", ru ? "Workflow открыт" : "Workflow loaded");
                  if (result === "downloaded") controller.bridge.toast("info", ru ? "Workflow скачан" : "Workflow downloaded");
                });
            } else {
              void copyArtifact(artifact).then((result) => {
                controller.bridge.toast(
                  "success",
                  result === "copied"
                    ? ru ? "JSON скопирован" : "JSON copied"
                    : ru ? "JSON скачан" : "JSON downloaded"
                );
              });
            }
          }}
        >
          {artifact.kind === "workflow"
            ? ru ? "Открыть workflow" : "Open workflow"
            : artifact.kind === "fragment"
              ? ru ? "Скопировать фрагмент JSON" : "Copy fragment JSON"
              : ru ? "Скопировать рецепт JSON" : "Copy recipe JSON"}
          {artifacts.length > 1 ? ` · ${artifact.title}` : ""}
        </button>
      ))}
    </section>
  );
}

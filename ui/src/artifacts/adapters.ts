import { z } from "zod";

import type { ComfyBridge } from "../bridge/ComfyBridge";

const objectSchema = z.record(z.unknown());

export interface ArticleArtifact {
  id: string;
  kind: "recipe" | "fragment" | "workflow";
  title: string;
  payload: Record<string, unknown>;
}

function asObjects(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) {
    return value.flatMap((entry) => asObjects(entry));
  }
  const parsed = objectSchema.safeParse(value);
  return parsed.success ? [parsed.data] : [];
}

function text(source: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return undefined;
}

function hasArray(source: Record<string, unknown>, key: string): boolean {
  return Array.isArray(source[key]);
}

export function decodeArticleArtifacts(
  recipeData: unknown,
  workflowData: unknown
): ArticleArtifact[] {
  const result: ArticleArtifact[] = [];
  const seen = new Set<string>();
  const workflowByRecipe = new Map<string, { id: string; title: string }>();
  const add = (artifact: ArticleArtifact) => {
    const key = `${artifact.kind}:${artifact.id}`;
    if (!seen.has(key)) {
      seen.add(key);
      result.push(artifact);
    }
  };

  for (const source of asObjects(recipeData)) {
    const isFragment = hasArray(source, "nodes") && hasArray(source, "connections");
    const id =
      text(source, "fragmentId", "fragment_id", "recipeId", "recipe_id", "id") ??
      `recipe-${result.length + 1}`;
    add({
      id,
      kind: isFragment ? "fragment" : "recipe",
      title: text(source, "title", "label") ?? id,
      payload: source
    });
    const recipeId = text(source, "recipeId", "recipe_id");
    const workflowReference = objectSchema.safeParse(source.workflow);
    const workflowId = workflowReference.success
      ? text(workflowReference.data, "id", "workflowId", "workflow_id")
      : undefined;
    if (recipeId && workflowId) {
      workflowByRecipe.set(recipeId, {
        id: workflowId,
        title: text(source, "title", "label") ?? workflowId
      });
    }
    for (const nested of asObjects(source.fragmentData ?? source.fragment_data)) {
      const nestedId = text(nested, "fragmentId", "fragment_id", "id") ?? `${id}:fragment`;
      add({ id: nestedId, kind: "fragment", title: text(nested, "title") ?? nestedId, payload: nested });
    }
    for (const nested of asObjects(source.workflowData ?? source.workflow_data)) {
      const embedded = objectSchema.safeParse(nested.workflow ?? nested.data);
      const payload = embedded.success ? embedded.data : nested;
      const nestedId = workflowId ??
        text(nested, "workflowId", "workflow_id", "id") ??
        `${id}:workflow`;
      add({
        id: nestedId,
        kind: "workflow",
        title: text(source, "title", "label") ?? text(nested, "title", "label") ?? nestedId,
        payload
      });
    }
  }

  for (const source of asObjects(workflowData)) {
    const embedded = objectSchema.safeParse(source.workflow ?? source.data);
    const payload = embedded.success ? embedded.data : source;
    const extra = objectSchema.safeParse(payload.extra);
    const wizard = extra.success ? objectSchema.safeParse(extra.data.nodes_wizard) : undefined;
    const recipeId = wizard?.success ? text(wizard.data, "recipeId", "recipe_id") : undefined;
    const referenced = recipeId ? workflowByRecipe.get(recipeId) : undefined;
    const id = text(source, "workflowId", "workflow_id", "id") ??
      referenced?.id ??
      `workflow-${result.length + 1}`;
    add({
      id,
      kind: "workflow",
      title: text(source, "title", "label") ?? referenced?.title ?? id,
      payload
    });
  }
  return result;
}

function downloadJson(payload: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.replace(/[^a-z0-9._-]+/gi, "-");
  link.click();
  URL.revokeObjectURL(url);
}

export async function copyArtifact(artifact: ArticleArtifact): Promise<"copied" | "downloaded"> {
  const json = JSON.stringify(artifact.payload, null, 2);
  try {
    await navigator.clipboard.writeText(json);
    return "copied";
  } catch {
    downloadJson(artifact.payload, `${artifact.id}.json`);
    return "downloaded";
  }
}

function isWorkflow(payload: Record<string, unknown>): boolean {
  return (
    Array.isArray(payload.nodes) &&
    (Array.isArray(payload.links) || payload.links === undefined) &&
    !Array.isArray(payload.connections)
  );
}

export async function openWorkflowArtifact(
  artifact: ArticleArtifact,
  bridge: ComfyBridge,
  locale: string
): Promise<"loaded" | "downloaded" | "cancelled"> {
  if (!isWorkflow(artifact.payload)) {
    downloadJson(artifact.payload, `${artifact.id}.json`);
    return "downloaded";
  }
  const ru = locale.startsWith("ru");
  const accepted = await bridge.confirm(
    ru ? "Открыть workflow в новой вкладке?" : "Open workflow in a new tab?",
    ru
      ? "Wizard создаст временную вкладку. Текущий граф и несохранённые изменения останутся без изменений."
      : "Wizard will create a temporary tab. Your current graph and unsaved changes stay untouched."
  );
  if (!accepted) return "cancelled";
  if (await bridge.openTemporaryWorkflow(artifact.payload)) return "loaded";
  downloadJson(artifact.payload, `${artifact.id}.json`);
  return "downloaded";
}

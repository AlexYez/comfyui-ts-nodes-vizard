import type { ComfyNodeLike } from "../types/comfy";

export function exactNodeClassType(node: ComfyNodeLike): string | null {
  if (typeof node.comfyClass === "string" && node.comfyClass.trim()) {
    return node.comfyClass.trim();
  }

  // `type` is only a safe fallback for normal nodes when a caller can validate it
  // against /object_info. Notes, groups and subgraphs also have a `type`.
  return null;
}

export function exactRuntimeClassType(
  node: ComfyNodeLike,
  runtimeClassTypes: ReadonlySet<string>
): string | null {
  const comfyClass = exactNodeClassType(node);
  if (comfyClass) return comfyClass;
  if (typeof node.type !== "string") return null;
  const type = node.type.trim();
  return type && runtimeClassTypes.has(type) ? type : null;
}


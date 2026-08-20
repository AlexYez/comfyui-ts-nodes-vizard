import type { NodeKey } from "../types/contracts";

const SEP = "\u001f";

export function normalisePythonModule(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed || undefined;
}

export function inferPackageId(pythonModule: string | undefined): string | undefined {
  const module = normalisePythonModule(pythonModule);
  if (!module) return undefined;
  if (
    module === "nodes" ||
    module.startsWith("comfy_extras.") ||
    module.startsWith("comfy_api_nodes.")
  ) {
    return "comfy-core";
  }
  const custom = module.match(/^custom_nodes[./]([^./]+)/);
  if (custom?.[1]) return custom[1];
  return undefined;
}

export function normaliseNodeKey(key: NodeKey): NodeKey {
  const pythonModule = normalisePythonModule(key.pythonModule);
  return {
    classType: key.classType.trim(),
    kind: key.kind,
    pythonModule,
    packageId: key.packageId?.trim() || inferPackageId(pythonModule)
  };
}

/** Composite key. Missing provenance remains explicit and can never equal a populated field. */
export function serialiseNodeKey(key: NodeKey): string {
  const normalised = normaliseNodeKey(key);
  return [
    normalised.kind,
    normalised.packageId ?? "",
    normalised.pythonModule ?? "",
    normalised.classType
  ].join(SEP);
}

export function sameNodeProvenance(article: NodeKey, runtime: NodeKey): boolean {
  const left = normaliseNodeKey(article);
  const right = normaliseNodeKey(runtime);
  if (left.kind !== right.kind || left.classType !== right.classType) return false;
  if ((left.packageId || right.packageId) && left.packageId !== right.packageId) return false;
  if (
    (left.pythonModule || right.pythonModule) &&
    left.pythonModule !== right.pythonModule
  ) {
    return false;
  }
  return true;
}

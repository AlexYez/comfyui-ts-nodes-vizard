import type { RuntimeNodeDefinition } from "../types/contracts";

export interface RuntimeOverlayPort {
  name: string;
  type: string;
  mode: "required" | "optional" | "output";
  list: boolean;
  tooltip?: string;
  constraints: Array<{ key: string; value: string }>;
}

export interface RuntimeOverlayData {
  classType: string;
  category: string;
  packageId?: string;
  pythonModule?: string;
  deprecated: boolean;
  experimental: boolean;
  apiNode: boolean;
  schemaHash: string;
  inputs: RuntimeOverlayPort[];
  outputs: RuntimeOverlayPort[];
}

function displayValue(value: unknown): string {
  if (value === null) return "null";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  if (value && typeof value === "object" && String(value) !== "[object Object]") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "?";
  }
}

function constraints(
  value: Readonly<Record<string, unknown>> | undefined
): RuntimeOverlayPort["constraints"] {
  return Object.entries(value ?? {})
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
    .map(([key, entry]) => ({ key, value: displayValue(entry) }));
}

export function runtimeOverlayData(runtime: RuntimeNodeDefinition): RuntimeOverlayData {
  return {
    classType: runtime.classType,
    category: runtime.category,
    packageId: runtime.packageId,
    pythonModule: runtime.pythonModule,
    deprecated: runtime.deprecated,
    experimental: runtime.experimental,
    apiNode: runtime.apiNode,
    schemaHash: runtime.schemaHash,
    inputs: runtime.inputs.map((port) => ({
      name: port.name,
      type: port.type,
      mode: port.optional ? "optional" : "required",
      list: Boolean(port.isList),
      tooltip: port.tooltip,
      constraints: constraints(port.constraints)
    })),
    outputs: runtime.outputs.map((port) => ({
      name: port.name,
      type: port.type,
      mode: "output",
      list: Boolean(port.isList),
      tooltip: port.tooltip,
      constraints: constraints(port.constraints)
    }))
  };
}

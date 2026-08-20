import { z } from "zod";

import type {
  RuntimeNodeDefinition,
  RuntimePort
} from "../types/contracts";
import { inferPackageId } from "./nodeKey";

const objectInfoSchema = z.record(z.record(z.unknown()));

class LosslessJsonNumber {
  readonly raw: string;

  constructor(raw: string) {
    this.raw = raw;
  }

  toString(): string {
    return this.raw;
  }
}

const JSON_NUMBER = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/;

function isLosslessNumber(value: unknown): value is LosslessJsonNumber {
  return value instanceof LosslessJsonNumber;
}

/** Preserves JSON number lexemes (`8.0`, uint64 maxima) needed for Python hash parity. */
export function parseObjectInfoText(text: string): unknown {
  let encoded = "";
  let inString = false;
  let escaped = false;
  for (let index = 0; index < text.length;) {
    const character = text[index] ?? "";
    if (inString) {
      encoded += character;
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      index += 1;
      continue;
    }
    if (character === '"') {
      inString = true;
      encoded += character;
      index += 1;
      continue;
    }
    if (character === "-" || (character >= "0" && character <= "9")) {
      const match = text.slice(index).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
      if (match?.[0]) {
        encoded += `{"$nodesWizardNumber":${JSON.stringify(match[0])}}`;
        index += match[0].length;
        continue;
      }
    }
    encoded += character;
    index += 1;
  }
  return JSON.parse(encoded, (_key, value: unknown) => {
    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).length === 1 &&
      typeof (value as Record<string, unknown>).$nodesWizardNumber === "string" &&
      JSON_NUMBER.test((value as Record<string, string>).$nodesWizardNumber ?? "")
    ) {
      return new LosslessJsonNumber(
        (value as Record<string, string>).$nodesWizardNumber ?? "0"
      );
    }
    return value;
  });
}

const STABLE_CONSTRAINT_KEYS = [
  "min",
  "max",
  "step",
  "round",
  "multiline",
  "dynamicPrompts",
  "forceInput",
  "defaultInput",
  "lazy",
  "rawLink",
  "socketless",
  "advanced",
  "control_after_generate"
] as const;

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function isScalar(
  value: unknown
): value is string | number | boolean | LosslessJsonNumber {
  return (
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value)) ||
    isLosslessNumber(value)
  );
}

/** Mirrors tools/catalog.py `_legacy_input_type` exactly for JSON values. */
function legacyInputType(definition: unknown): string {
  if (definition !== null && typeof definition === "object" && !Array.isArray(definition)) {
    const source = definition as Record<string, unknown>;
    const raw = source.type ?? source.data_type ?? source.io_type;
    if (typeof raw === "string") return raw;
    const choices = source.options ?? source.values;
    if (Array.isArray(choices)) return "COMBO";
  }
  if (Array.isArray(definition) && definition.length > 0) {
    const first = definition[0];
    if (typeof first === "string") return first;
    if (Array.isArray(first)) return "COMBO";
  }
  if (typeof definition === "string") return definition;
  return "UNKNOWN";
}

function inputOptions(definition: unknown): Record<string, unknown> {
  if (definition !== null && typeof definition === "object" && !Array.isArray(definition)) {
    return definition as Record<string, unknown>;
  }
  if (Array.isArray(definition) && definition.length > 1) return asRecord(definition[1]);
  return {};
}

interface NormalizedInput {
  name: string;
  type: string;
  section: "required" | "optional" | "hidden";
  required: boolean;
  constraints?: Record<string, string | number | boolean | LosslessJsonNumber | null>;
}

interface NormalizedOutput {
  name: string;
  type: string;
  list: boolean;
  tooltip?: string;
}

export interface NormalizedNodeSchema {
  nodeId: string;
  pythonModule: string | null;
  inputs: NormalizedInput[];
  outputs: NormalizedOutput[];
  flags: { deprecated: boolean; experimental: boolean; api_node: boolean };
}

function normalizeInput(
  name: string,
  section: NormalizedInput["section"],
  definition: unknown
): NormalizedInput {
  const type = legacyInputType(definition);
  const options = inputOptions(definition);
  const constraints: Record<
    string,
    string | number | boolean | LosslessJsonNumber | null
  > = {};
  for (const key of STABLE_CONSTRAINT_KEYS) {
    const value = options[key];
    if (isScalar(value)) constraints[key] = value;
  }
  // Combo choices and defaults are installation-dependent and excluded in Python too.
  if (type !== "COMBO" && Object.hasOwn(options, "default")) {
    const value = options.default;
    if (value === null || isScalar(value)) constraints.default = value;
  }
  return {
    name,
    type,
    section,
    required: section === "required",
    ...(Object.keys(constraints).length === 0 ? {} : { constraints })
  };
}

/** Byte-for-byte structural model shared with tools/catalog.py `normalize_node_schema`. */
export function normalizeNodeSchema(
  nodeId: string,
  raw: Readonly<Record<string, unknown>>
): NormalizedNodeSchema {
  const inputRoot = asRecord(raw.input);
  const inputOrder = asRecord(raw.input_order);
  const inputs: NormalizedInput[] = [];
  for (const section of ["required", "optional", "hidden"] as const) {
    const definitions = asRecord(inputRoot[section]);
    const ordered = Array.isArray(inputOrder[section]) ? inputOrder[section] : [];
    const names = ordered.filter(
      (name): name is string => typeof name === "string" && Object.hasOwn(definitions, name)
    );
    for (const name of Object.keys(definitions)) {
      if (!names.includes(name)) names.push(name);
    }
    for (const name of names) inputs.push(normalizeInput(name, section, definitions[name]));
  }

  const outputTypes = Array.isArray(raw.output) ? raw.output : [];
  const outputNames = Array.isArray(raw.output_name) ? raw.output_name : [];
  const outputLists = Array.isArray(raw.output_is_list) ? raw.output_is_list : [];
  const outputTooltips = Array.isArray(raw.output_tooltips) ? raw.output_tooltips : [];
  const outputs: NormalizedOutput[] = outputTypes.map((outputType, index) => {
    const name = typeof outputNames[index] === "string"
      ? outputNames[index]
      : String(outputType);
    const tooltip = outputTooltips[index];
    return {
      name,
      type: String(outputType),
      list: Boolean(outputLists[index]),
      ...(typeof tooltip === "string" ? { tooltip } : {})
    };
  });

  return {
    nodeId,
    pythonModule: typeof raw.python_module === "string" ? raw.python_module : null,
    inputs,
    outputs,
    flags: {
      deprecated: Boolean(raw.deprecated),
      experimental: Boolean(raw.experimental),
      api_node: Boolean(raw.api_node)
    }
  };
}

/** Canonical JSON: sorted keys, compact separators, UTF-8 when encoded. */
export function canonicalJson(value: unknown): string {
  if (isLosslessNumber(value)) return value.raw;
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, entry]) => entry !== undefined)
    // Default JS sort is deterministic code-unit order; all schema/signature keys are ASCII.
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
  return `{${entries
    .map(([key, entry]) => `${JSON.stringify(key)}:${canonicalJson(entry)}`)
    .join(",")}}`;
}

export async function schemaFingerprint(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(value));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  const hex = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return `sha256:${hex}`;
}

function runtimeInputs(normalized: NormalizedNodeSchema): RuntimePort[] {
  return normalized.inputs.map((input) => ({
    name: input.name,
    type: input.type,
    optional: !input.required,
    constraints: input.constraints
  }));
}

function runtimeOutputs(normalized: NormalizedNodeSchema): RuntimePort[] {
  return normalized.outputs.map((output) => ({
    name: output.name,
    type: output.type,
    optional: false,
    isList: output.list,
    tooltip: output.tooltip
  }));
}

export async function decodeObjectInfo(
  input: unknown
): Promise<Map<string, RuntimeNodeDefinition>> {
  const parsed = objectInfoSchema.parse(input);
  const result = new Map<string, RuntimeNodeDefinition>();

  await Promise.all(Object.entries(parsed).map(async ([classType, source]) => {
    const normalized = normalizeNodeSchema(classType, source);
    const pythonModule = normalized.pythonModule ?? undefined;
    result.set(classType, {
      classType,
      kind: "server",
      packageId: inferPackageId(pythonModule),
      displayName: asString(source.display_name, classType),
      description: asString(source.description),
      category: asString(source.category, "uncategorized"),
      pythonModule,
      deprecated: normalized.flags.deprecated,
      experimental: normalized.flags.experimental,
      apiNode: normalized.flags.api_node,
      inputs: runtimeInputs(normalized),
      outputs: runtimeOutputs(normalized),
      schemaHash: await schemaFingerprint(normalized),
      raw: Object.freeze({ ...source })
    });
  }));

  return result;
}

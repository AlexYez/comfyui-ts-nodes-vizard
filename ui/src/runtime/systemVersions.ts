export interface ComfySystemVersions {
  backend?: string;
  frontend?: string;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function nonEmptyText(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Decodes the official ComfyUI 0.32 `/system_stats` package-version shape. */
export function decodeSystemVersions(input: unknown): ComfySystemVersions {
  const root = record(input);
  const system = record(root?.system);
  if (!system) return {};

  const packages = Array.isArray(system.comfy_package_versions)
    ? system.comfy_package_versions
    : [];
  const frontendPackage = packages
    .map(record)
    .find((entry) => entry?.name === "comfyui-frontend-package");

  return {
    backend: nonEmptyText(system.comfyui_version),
    frontend: nonEmptyText(frontendPackage?.installed)
  };
}

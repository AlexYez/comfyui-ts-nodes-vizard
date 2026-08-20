import { describe, expect, it } from "vitest";

import { decodeSystemVersions } from "./systemVersions";

describe("official /system_stats version decoder", () => {
  it("reads backend and installed frontend package versions from the 0.32 shape", () => {
    expect(decodeSystemVersions({
      system: {
        comfyui_version: "0.32.0",
        comfy_package_versions: [
          { name: "comfyui-workflow-templates", installed: "0.1.70", required: "0.1.60" },
          {
            name: "comfyui-frontend-package",
            installed: "1.48.7",
            required: "1.47.0"
          }
        ]
      },
      devices: []
    })).toEqual({ backend: "0.32.0", frontend: "1.48.7" });
  });

  it("uses installed, never required or unrelated legacy-looking fields", () => {
    expect(decodeSystemVersions({
      system: {
        comfyui_version: "0.32.0",
        frontend_version: "unsafe-fallback",
        comfy_package_versions: [{
          name: "comfyui-frontend-package",
          installed: null,
          required: "9.9.9"
        }]
      }
    })).toEqual({ backend: "0.32.0", frontend: undefined });
  });

  it("fails soft for malformed payloads", () => {
    expect(decodeSystemVersions(null)).toEqual({});
    expect(decodeSystemVersions({ system: { comfy_package_versions: "invalid" } }))
      .toEqual({ backend: undefined, frontend: undefined });
  });
});

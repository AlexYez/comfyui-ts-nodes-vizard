import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { render, screen } from "@testing-library/react";

import type { RuntimeNodeDefinition } from "../types/contracts";
import { runtimeOverlayData } from "./runtimeOverlayData";
import { RuntimeOverlay } from "./RuntimeOverlay";

describe("runtime overlay data", () => {
  it("keeps live category, status, ports, stable constraints and list outputs", () => {
    const runtime: RuntimeNodeDefinition = {
      classType: "LiveNode",
      kind: "server",
      packageId: "comfy-core",
      pythonModule: "nodes",
      displayName: "Live Node",
      description: "",
      category: "image/live",
      deprecated: true,
      experimental: false,
      apiNode: true,
      inputs: [{
        name: "strength",
        type: "FLOAT",
        optional: false,
        constraints: { min: 0, max: 1, step: 0.05 }
      }],
      outputs: [{ name: "images", type: "IMAGE", optional: false, isList: true }],
      schemaHash: `sha256:${"a".repeat(64)}`,
      raw: {}
    };
    expect(runtimeOverlayData(runtime)).toMatchObject({
      category: "image/live",
      deprecated: true,
      apiNode: true,
      inputs: [{
        name: "strength",
        mode: "required",
        constraints: [
          { key: "max", value: "1" },
          { key: "min", value: "0" },
          { key: "step", value: "0.05" }
        ]
      }],
      outputs: [{ name: "images", mode: "output", list: true }]
    });
  });

  it("renders live schema independently from editorial Markdown", () => {
    const runtime: RuntimeNodeDefinition = {
      classType: "RuntimeOnlyNode",
      kind: "server",
      displayName: "Runtime only",
      description: "",
      category: "runtime/category",
      deprecated: false,
      experimental: true,
      apiNode: true,
      inputs: [{ name: "count", type: "INT", optional: true, constraints: { min: 1 } }],
      outputs: [{ name: "result", type: "IMAGE", optional: false }],
      schemaHash: `sha256:${"b".repeat(64)}`,
      raw: {}
    };
    render(createElement(RuntimeOverlay, { runtime, locale: "ru" }));
    expect(screen.getByTestId("runtime-overlay")).toHaveTextContent("Живая схема ComfyUI");
    expect(screen.getByTestId("runtime-overlay")).toHaveTextContent("runtime/category");
    expect(screen.getByTestId("runtime-overlay")).toHaveTextContent("необязательный");
    expect(screen.getByTestId("runtime-overlay")).toHaveTextContent("min: 1");
    expect(screen.getByTestId("runtime-overlay")).toHaveTextContent("API node");
  });
});

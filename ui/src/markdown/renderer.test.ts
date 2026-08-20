import { renderSafeMarkdown } from "./renderer";
import { describe, expect, it } from "vitest";

describe("safe Markdown media", () => {
  it("blocks passive remote media requests and hardens external links", async () => {
    const html = await renderSafeMarkdown(
      '<img src="https://tracker.invalid/pixel.png" srcset="https://tracker.invalid/2x.png 2x">' +
        '<video src="https://tracker.invalid/a.mp4" poster="https://tracker.invalid/p.jpg"></video>' +
        '<a href="https://docs.comfy.org/">Docs</a>',
      `${window.location.origin}/extensions/comfyui-ts-nodes-vizard/data/`
    );
    const template = document.createElement("template");
    template.innerHTML = html;
    expect(template.content.querySelector("img")?.hasAttribute("src")).toBe(false);
    expect(template.content.querySelector("img")?.hasAttribute("srcset")).toBe(false);
    expect(template.content.querySelector("video")?.hasAttribute("src")).toBe(false);
    expect(template.content.querySelector("video")?.hasAttribute("poster")).toBe(false);
    expect(template.content.querySelector("a")?.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("keeps same-origin catalog media", async () => {
    const html = await renderSafeMarkdown(
      "![local](images/example.png)",
      `${window.location.origin}/extensions/comfyui-ts-nodes-vizard/data/`
    );
    const template = document.createElement("template");
    template.innerHTML = html;
    expect(template.content.querySelector("img")?.getAttribute("src")).toBe("images/example.png");
  });

  it("blocks same-origin media outside the catalog asset directory", async () => {
    const html = await renderSafeMarkdown(
      "![not-an-asset](/api/view?filename=private.png)",
      `${window.location.origin}/extensions/comfyui-ts-nodes-vizard/data/`
    );
    const template = document.createElement("template");
    template.innerHTML = html;
    expect(template.content.querySelector("img")?.hasAttribute("src")).toBe(false);
  });

  it("removes arbitrary HTML, CSS, forms, and subtitle beacons", async () => {
    const html = await renderSafeMarkdown(
      '<style>@import url(https://tracker.invalid/a.css)</style>' +
        '<form action="https://tracker.invalid/"><input name="secret"></form>' +
        '<video><track default src="https://tracker.invalid/a.vtt"></video>',
      `${window.location.origin}/extensions/comfyui-ts-nodes-vizard/data/`
    );
    const template = document.createElement("template");
    template.innerHTML = html;
    expect(template.content.querySelector("style, form, input, track")).toBeNull();
    expect(html).not.toContain("tracker.invalid");
  });
});

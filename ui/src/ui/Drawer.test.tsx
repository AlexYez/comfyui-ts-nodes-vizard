import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WizardController } from "../app/controller";
import { ComfyBridge } from "../bridge/ComfyBridge";
import { MemoryCatalogStore } from "../catalog/storage";
import { Drawer } from "./Drawer";

function fixture() {
  const bridge = new ComfyBridge({ registerExtension: vi.fn() });
  vi.spyOn(bridge, "fetchObjectInfo").mockResolvedValue(new Map());
  vi.spyOn(bridge, "fetchSystemVersions").mockResolvedValue({});
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    schemaVersion: "1.0", catalogVersion: "1.0.0", locale: "ru", articles:
      Array.from({ length: 101 }, (_, id) => ({
        manifest: { articleId: `article.${id}`, locale: "ru", kind: "concept" },
        title: `Article ${String(id).padStart(3, "0")}`, body: "Body"
      }))
  })));
  return { controller: new WizardController({ bridge, fetch: fetcher, store: new MemoryCatalogStore(), locale: "ru" }), fetcher };
}
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); });

describe("drawer resource bounds", () => {
  it("loads only on open, limits catalog rows, and removes content on close", async () => {
    const { controller, fetcher } = fixture();
    const { container } = render(<Drawer controller={controller} />);
    expect(container).toBeEmptyDOMElement();
    expect(fetcher).not.toHaveBeenCalled();
    await act(async () => { controller.open(); await controller.initialise(); });
    act(() => controller.showCatalog());
    expect(container.querySelectorAll(".nw-result")).toHaveLength(40);
    fireEvent.click(screen.getByText("Далее"));
    expect(screen.getByText("Article 040")).toBeInTheDocument();
    const release = vi.spyOn(controller.getSnapshot().registry!, "releaseSearch");
    act(() => controller.close());
    expect(container).toBeEmptyDOMElement();
    expect(release).toHaveBeenCalledOnce();
    await act(async () => { controller.open(); });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it("ignores a search response that arrives after navigation", async () => {
    const { controller } = fixture();
    render(<Drawer controller={controller} />);
    await act(async () => { controller.open(); await controller.initialise(); });
    let resolve!: (value: []) => void;
    const search = vi.spyOn(controller.getSnapshot().registry!, "searchAsync")
      .mockImplementation(() => new Promise((done) => { resolve = done; }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "test" } });
    await waitFor(() => expect(search).toHaveBeenCalledOnce());
    act(() => controller.selectArticle("article.1"));
    await act(async () => resolve([]));
    expect(screen.getByRole("heading", { name: "Article 001", level: 1 })).toBeInTheDocument();
    expect(screen.queryByText("Ничего не найдено")).not.toBeInTheDocument();
  });
  it("aborts loading on close and can start a fresh request", async () => {
    const { controller, fetcher } = fixture();
    let signal: AbortSignal | undefined;
    fetcher.mockImplementationOnce((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      signal = options.signal as AbortSignal;
      signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    render(<Drawer controller={controller} />);
    act(() => controller.open());
    await waitFor(() => expect(signal).toBeDefined());
    act(() => controller.close());
    expect(signal?.aborted).toBe(true);
    await act(async () => { controller.open(); await controller.initialise(); });
    expect(controller.getSnapshot().phase).toBe("ready");
  });
});

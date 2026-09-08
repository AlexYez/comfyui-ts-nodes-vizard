import { afterEach, describe, expect, it, vi } from "vitest";
import { BackgroundTask, runBackground } from "./background";

class FakeWorker {
  static instances: FakeWorker[] = [];
  onmessage?: (event: { data: unknown }) => void;
  onerror?: () => void;
  onmessageerror?: () => void;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() { FakeWorker.instances.push(this); }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); FakeWorker.instances = []; });

describe("background task lifecycle", () => {
  it("does not create a worker before a request and rejects pending work on disposal", async () => {
    vi.stubGlobal("Worker", FakeWorker);
    const task = new BackgroundTask();
    expect(FakeWorker.instances).toHaveLength(0);
    const pending = task.request("index", []);
    const rejection = expect(pending).rejects.toThrow("cancelled");
    task.dispose();
    await rejection;
    expect(FakeWorker.instances[0]?.terminate).toHaveBeenCalledOnce();
    await expect(task.request("search", {})).rejects.toThrow("cancelled");
    expect(FakeWorker.instances).toHaveLength(1);
  });
  it("matches responses by request id and terminates one-shot workers", async () => {
    vi.stubGlobal("Worker", FakeWorker);
    const pending = runBackground("catalog", "text");
    FakeWorker.instances[0]?.onmessage?.({ data: { id: 1, value: { articles: [] } } });
    await expect(pending).resolves.toEqual({ articles: [] });
    expect(FakeWorker.instances[0]?.terminate).toHaveBeenCalledOnce();
  });
  it("terminates on abort, including an already aborted request", async () => {
    vi.stubGlobal("Worker", FakeWorker);
    const controller = new AbortController();
    const pending = runBackground("runtime", "{}", controller.signal);
    const rejection = expect(pending).rejects.toThrow("cancelled");
    controller.abort();
    await rejection;
    await expect(runBackground("runtime", "{}", controller.signal)).rejects.toBeDefined();
    expect(FakeWorker.instances).toHaveLength(1);
  });
  it("rejects worker failures and bounds a hung request", async () => {
    vi.stubGlobal("Worker", FakeWorker);
    vi.useFakeTimers();
    const pending = runBackground("index", []);
    const rejection = expect(pending).rejects.toThrow("timed out");
    await vi.advanceTimersByTimeAsync(60_000);
    await rejection;
    expect(vi.getTimerCount()).toBe(0);
    const failure = runBackground("index", []);
    const failed = expect(failure).rejects.toThrow("failed");
    FakeWorker.instances[1]?.onerror?.();
    await failed;
    expect(vi.getTimerCount()).toBe(0);
  });
});

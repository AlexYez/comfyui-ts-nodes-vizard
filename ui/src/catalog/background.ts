/** Workers are created only in response to an explicit Wizard action. */
export class BackgroundTask {
  #worker?: Worker;
  #nextId = 0;
  #disposed = false;
  #pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>();

  request<T>(operation: string, payload: unknown): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      try {
        if (this.#disposed) throw new Error("Wizard background processing cancelled");
        if (!this.#worker) {
          this.#worker = new Worker(new URL("./background.worker.ts", import.meta.url), { type: "module" });
          this.#worker.onmessage = (event: MessageEvent<{ id: number; value?: unknown; error?: string }>) => {
            const pending = this.#pending.get(event.data.id);
            if (!pending) return;
            this.#pending.delete(event.data.id);
            clearTimeout(pending.timer);
            if (event.data.error) pending.reject(new Error(event.data.error));
            else pending.resolve(event.data.value);
          };
          this.#worker.onerror = () => this.dispose(new Error("Wizard background processing failed"));
          this.#worker.onmessageerror = () => this.dispose(new Error("Wizard background response could not be read"));
        }
        const id = ++this.#nextId;
        const timer = setTimeout(() => this.dispose(new Error("Wizard background processing timed out")), 60_000);
        this.#pending.set(id, { resolve: (value) => resolve(value as T), reject, timer });
        this.#worker.postMessage({ id, operation, payload });
      } catch (error) {
        this.dispose(error instanceof Error ? error : new Error(String(error)));
        reject(error);
      }
    });
  }

  dispose(error = new Error("Wizard background processing cancelled")): void {
    this.#disposed = true;
    this.#worker?.terminate();
    this.#worker = undefined;
    for (const pending of this.#pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.#pending.clear();
  }
}

export async function runBackground<T>(operation: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  signal?.throwIfAborted();
  const task = new BackgroundTask();
  const abort = () => task.dispose(new Error("Wizard background processing cancelled"));
  signal?.addEventListener("abort", abort, { once: true });
  try { return await task.request<T>(operation, payload); }
  finally { signal?.removeEventListener("abort", abort); task.dispose(); }
}

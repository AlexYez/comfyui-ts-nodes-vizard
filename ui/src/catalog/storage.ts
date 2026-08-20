import type { CatalogDocument } from "../types/contracts";

export type CatalogRecordOrigin = "bundled" | "signed-update";

export interface StoredCatalogRecord {
  catalog: CatalogDocument;
  origin: CatalogRecordOrigin;
  storedAt: string;
  sha256?: string;
  keyId?: string;
}

export interface CatalogStore {
  getActive(): Promise<StoredCatalogRecord | null>;
  getPrevious(): Promise<StoredCatalogRecord | null>;
  commit(record: StoredCatalogRecord): Promise<void>;
  rollback(): Promise<StoredCatalogRecord | null>;
}

const DB_NAME = "comfyui-ts-nodes-vizard";
const STORE_NAME = "catalog-snapshots";

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

export class IndexedDbCatalogStore implements CatalogStore {
  readonly #openDatabase: () => Promise<IDBDatabase>;

  constructor(indexedDb: IDBFactory | undefined = globalThis.indexedDB) {
    this.#openDatabase = async () => {
      if (!indexedDb) throw new Error("IndexedDB is unavailable");
      const request = indexedDb.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) {
          request.result.createObjectStore(STORE_NAME);
        }
      };
      return requestResult(request);
    };
  }

  async getActive(): Promise<StoredCatalogRecord | null> {
    return this.#get("active");
  }

  async getPrevious(): Promise<StoredCatalogRecord | null> {
    return this.#get("previous");
  }

  async commit(record: StoredCatalogRecord): Promise<void> {
    const database = await this.#openDatabase();
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        const read = store.get("active");
        read.onsuccess = () => {
          if (read.result) store.put(read.result, "previous");
          store.put(record, "active");
        };
        transaction.oncomplete = () => resolve();
        transaction.onerror = () =>
          reject(transaction.error ?? new Error("Could not store catalog"));
        transaction.onabort = () =>
          reject(transaction.error ?? new Error("Catalog transaction aborted"));
      });
    } finally {
      database.close();
    }
  }

  async rollback(): Promise<StoredCatalogRecord | null> {
    const database = await this.#openDatabase();
    try {
      return await new Promise<StoredCatalogRecord | null>((resolve, reject) => {
        let restored: StoredCatalogRecord | null = null;
        const transaction = database.transaction(STORE_NAME, "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        const previousRequest = store.get("previous");
        const activeRequest = store.get("active");
        let reads = 0;
        const maybeSwap = () => {
          reads += 1;
          if (reads !== 2) return;
          const previous = previousRequest.result as StoredCatalogRecord | undefined;
          const active = activeRequest.result as StoredCatalogRecord | undefined;
          if (!previous) return;
          restored = previous;
          store.put(previous, "active");
          if (active) store.put(active, "previous");
          else store.delete("previous");
        };
        previousRequest.onsuccess = maybeSwap;
        activeRequest.onsuccess = maybeSwap;
        transaction.oncomplete = () => resolve(restored);
        transaction.onerror = () =>
          reject(transaction.error ?? new Error("Could not roll back catalog"));
        transaction.onabort = () =>
          reject(transaction.error ?? new Error("Catalog rollback aborted"));
      });
    } finally {
      database.close();
    }
  }

  async #get(key: "active" | "previous"): Promise<StoredCatalogRecord | null> {
    const database = await this.#openDatabase();
    try {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const value = await requestResult(transaction.objectStore(STORE_NAME).get(key));
      return (value as StoredCatalogRecord | undefined) ?? null;
    } finally {
      database.close();
    }
  }
}

export class MemoryCatalogStore implements CatalogStore {
  #active: StoredCatalogRecord | null = null;
  #previous: StoredCatalogRecord | null = null;

  async getActive(): Promise<StoredCatalogRecord | null> {
    return this.#active;
  }

  async getPrevious(): Promise<StoredCatalogRecord | null> {
    return this.#previous;
  }

  async commit(record: StoredCatalogRecord): Promise<void> {
    this.#previous = this.#active;
    this.#active = record;
  }

  async rollback(): Promise<StoredCatalogRecord | null> {
    if (!this.#previous) return null;
    [this.#active, this.#previous] = [this.#previous, this.#active];
    return this.#active;
  }
}

export class ResilientCatalogStore implements CatalogStore {
  readonly #primary: CatalogStore;
  readonly #fallback: CatalogStore;

  constructor(
    primary: CatalogStore = new IndexedDbCatalogStore(),
    fallback: CatalogStore = new MemoryCatalogStore()
  ) {
    this.#primary = primary;
    this.#fallback = fallback;
  }

  async getActive(): Promise<StoredCatalogRecord | null> {
    try {
      return await this.#primary.getActive();
    } catch {
      return this.#fallback.getActive();
    }
  }

  async getPrevious(): Promise<StoredCatalogRecord | null> {
    try {
      return await this.#primary.getPrevious();
    } catch {
      return this.#fallback.getPrevious();
    }
  }

  async commit(record: StoredCatalogRecord): Promise<void> {
    try {
      await this.#primary.commit(record);
    } catch {
      await this.#fallback.commit(record);
    }
  }

  async rollback(): Promise<StoredCatalogRecord | null> {
    try {
      return await this.#primary.rollback();
    } catch {
      return this.#fallback.rollback();
    }
  }
}

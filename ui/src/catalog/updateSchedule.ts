import type { CatalogUpdaterConfig } from "./updater";

const DAY_MS = 24 * 60 * 60 * 1000;
const LAST_CHECK_KEY = "nodes-wizard.update-last-check";
const UPDATES_ENABLED_KEY = "nodes-wizard.updates-enabled";

export function updateConfigurationReady(
  config: CatalogUpdaterConfig | undefined
): config is CatalogUpdaterConfig {
  return Boolean(
    config?.enabled &&
    config.manifestUrl.trim() &&
    Object.keys(config.publicKeys).length > 0 &&
    config.installedVersions?.comfyui &&
    config.installedVersions.frontend
  );
}

export class DailyUpdateSchedule {
  readonly #storage: Pick<Storage, "getItem" | "setItem"> | undefined;

  constructor(storage?: Pick<Storage, "getItem" | "setItem">) {
    try {
      this.#storage = storage ?? globalThis.localStorage;
    } catch {
      this.#storage = undefined;
    }
  }

  isDue(now = Date.now()): boolean {
    try {
      const last = Number(this.#storage?.getItem(LAST_CHECK_KEY));
      return !Number.isFinite(last) || last <= 0 || now - last >= DAY_MS;
    } catch {
      return true;
    }
  }

  markChecked(now = Date.now()): void {
    try {
      this.#storage?.setItem(LAST_CHECK_KEY, String(now));
    } catch {
      // Storage is an optimization only; updater verification remains unaffected.
    }
  }
}

/** Persistent user consent gate. Missing storage/default value means enabled. */
export class UpdatePreference {
  readonly #storage: Pick<Storage, "getItem" | "setItem"> | undefined;

  constructor(storage?: Pick<Storage, "getItem" | "setItem">) {
    try {
      this.#storage = storage ?? globalThis.localStorage;
    } catch {
      this.#storage = undefined;
    }
  }

  isEnabled(): boolean {
    try {
      return this.#storage?.getItem(UPDATES_ENABLED_KEY) !== "false";
    } catch {
      return true;
    }
  }

  setEnabled(enabled: boolean): void {
    try {
      this.#storage?.setItem(UPDATES_ENABLED_KEY, String(enabled));
    } catch {
      // The in-memory controller state still applies for this session.
    }
  }
}

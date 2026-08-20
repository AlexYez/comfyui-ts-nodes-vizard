import { CatalogLoader } from "../catalog/loader";
import { CatalogRegistry } from "../catalog/registry";
import { parseStoredCatalog } from "../catalog/schema";
import {
  ResilientCatalogStore,
  type CatalogStore,
  type StoredCatalogRecord
} from "../catalog/storage";
import {
  CatalogUpdater,
  DISABLED_UPDATE_CONFIG,
  type CatalogUpdateCandidate,
  type CatalogUpdaterConfig
} from "../catalog/updater";
import {
  DailyUpdateSchedule,
  UpdatePreference,
  updateConfigurationReady
} from "../catalog/updateSchedule";
import { ComfyBridge } from "../bridge/ComfyBridge";
import { exactNodeClassType } from "../runtime/identity";
import type { ComfyNodeLike } from "../types/comfy";
import type { CatalogDocument, LocaleCode, ResolvedArticle } from "../types/contracts";

export interface BoundedChangeList {
  total: number;
  items: string[];
}

export interface BoundedUpdateChanges {
  added: BoundedChangeList;
  updated: BoundedChangeList;
  deprecated: BoundedChangeList;
  removed: BoundedChangeList;
}

const UPDATE_CHANGE_LIMIT = 12;

function boundedChangeList(values: readonly string[]): BoundedChangeList {
  return { total: values.length, items: values.slice(0, UPDATE_CHANGE_LIMIT) };
}

export function boundedChanges(candidate: CatalogUpdateCandidate): BoundedUpdateChanges {
  const changes = candidate.manifest.changes;
  return {
    added: boundedChangeList(changes.added),
    updated: boundedChangeList(changes.updated),
    deprecated: boundedChangeList(changes.deprecated),
    removed: boundedChangeList(changes.removed)
  };
}

export function signedCatalogSize(candidate: CatalogUpdateCandidate): number {
  return candidate.manifest.artifacts.find((artifact) => artifact.path.endsWith("catalog.json"))?.size ?? 0;
}

function confirmationChanges(candidate: CatalogUpdateCandidate, ru: boolean): string {
  const groups: Array<[string, readonly string[]]> = [
    [ru ? "Добавлено" : "Added", candidate.manifest.changes.added],
    [ru ? "Обновлено" : "Updated", candidate.manifest.changes.updated],
    [ru ? "Устарело" : "Deprecated", candidate.manifest.changes.deprecated],
    [ru ? "Удалено" : "Removed", candidate.manifest.changes.removed]
  ];
  return groups
    .filter(([, values]) => values.length > 0)
    .map(([label, values]) => {
      const visible = values.slice(0, 6).join(", ");
      const remainder = values.length > 6 ? ` (+${values.length - 6})` : "";
      return `${label} (${values.length}): ${visible}${remainder}`;
    })
    .join("\n");
}

export function updateConfirmationMessage(
  candidate: CatalogUpdateCandidate,
  ru: boolean
): string {
  return [
    `${candidate.catalog.catalogVersion} · ${signedCatalogSize(candidate)} bytes`,
    candidate.manifest.changes.summary,
    confirmationChanges(candidate, ru)
  ].filter(Boolean).join("\n\n");
}

export interface WizardSnapshot {
  open: boolean;
  phase: "idle" | "loading" | "ready" | "error";
  locale: LocaleCode;
  query: string;
  registry?: CatalogRegistry;
  selected?: ResolvedArticle;
  error?: string;
  warnings: string[];
  catalogSource?: string;
  canGoBack: boolean;
  canGoForward: boolean;
  panel: "content" | "compatibility";
  versions: { backend?: string; frontend?: string };
  update:
    | { status: "disabled"; detail: string }
    | { status: "idle"; checkedAt?: string }
    | { status: "checking" }
    | { status: "up-to-date"; checkedAt: string }
    | {
        status: "available";
        version: string;
        summary: string;
        artifactSize: number;
        changes: BoundedUpdateChanges;
        checkedAt: string;
      }
    | { status: "error"; detail: string; checkedAt: string };
  updatesEnabled: boolean;
  updateConfigured: boolean;
  canRollback: boolean;
}

export interface WizardControllerOptions {
  bridge: ComfyBridge;
  store?: CatalogStore;
  catalogUrls?: string[];
  fetch?: typeof globalThis.fetch;
  locale?: LocaleCode;
  updateConfig?: CatalogUpdaterConfig;
  updateSchedule?: DailyUpdateSchedule;
  updatePreference?: UpdatePreference;
}

function detectLocale(bridge: ComfyBridge): LocaleCode {
  const setting = bridge.app.extensionManager?.setting?.get<string>("Comfy.Locale");
  const candidate = setting || document.documentElement.lang || navigator.language || "ru";
  return candidate.toLowerCase().startsWith("ru") ? "ru" : "en";
}

export class WizardController {
  readonly bridge: ComfyBridge;
  readonly #listeners = new Set<() => void>();
  readonly #store: CatalogStore;
  readonly #catalogUrls?: string[];
  readonly #fetch?: typeof globalThis.fetch;
  readonly #updateConfig: CatalogUpdaterConfig;
  readonly #updateSchedule: DailyUpdateSchedule;
  readonly #updatePreference: UpdatePreference;
  #effectiveUpdateConfig?: CatalogUpdaterConfig;
  #updater?: CatalogUpdater;
  #updateCheckController?: AbortController;
  #updateCheckGeneration = 0;
  #updateCandidate?: CatalogUpdateCandidate;
  #runtime = new Map<string, import("../types/contracts").RuntimeNodeDefinition>();
  #pendingClassType?: string;
  #initialisePromise?: Promise<void>;
  #history: Array<{ type: "article" | "classType"; value: string }> = [];
  #historyIndex = -1;
  #snapshot: WizardSnapshot;

  constructor(options: WizardControllerOptions) {
    this.bridge = options.bridge;
    this.#store = options.store ?? new ResilientCatalogStore();
    this.#catalogUrls = options.catalogUrls;
    this.#fetch = options.fetch;
    this.#updatePreference = options.updatePreference ?? new UpdatePreference();
    this.#snapshot = {
      open: false,
      phase: "idle",
      locale: options.locale ?? detectLocale(options.bridge),
      query: "",
      warnings: [],
      canGoBack: false,
      canGoForward: false,
      panel: "content",
      versions: {},
      update: {
        status: "disabled",
        detail: "Release update URL and signing keys are not configured."
      },
      updatesEnabled: this.#updatePreference.isEnabled(),
      updateConfigured: false,
      canRollback: false
    };
    this.#updateConfig = options.updateConfig ?? DISABLED_UPDATE_CONFIG;
    this.#updateSchedule = options.updateSchedule ?? new DailyUpdateSchedule();
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  readonly getSnapshot = (): WizardSnapshot => this.#snapshot;

  get catalogStore(): CatalogStore {
    return this.#store;
  }

  async initialise(): Promise<void> {
    if (this.#initialisePromise) return this.#initialisePromise;
    this.#initialisePromise = this.#doInitialise();
    return this.#initialisePromise;
  }

  open(request?: { classType?: string }): void {
    if (request?.classType) this.#pendingClassType = request.classType;
    this.#set({ open: true });
    void this.initialise().then(() => this.#resolvePending());
  }

  close(): void {
    this.#set({ open: false });
  }

  setQuery(query: string): void {
    this.#set({ query, panel: "content" });
  }

  showCatalog(): void {
    this.#set({ selected: undefined, query: "", panel: "content" });
  }

  showCompatibility(): void {
    this.#set({ panel: "compatibility", query: "" });
  }

  setLocale(locale: LocaleCode): void {
    const registry = this.#snapshot.registry;
    let selected = this.#snapshot.selected;
    if (registry && selected) {
      selected = selected.article.manifest.runtimeIdentity
        ? registry.resolveByClassType(
            selected.article.manifest.runtimeIdentity.classType,
            locale
          )
        : registry.resolveByArticleId(selected.article.manifest.articleId, locale);
    }
    this.#set({ locale, selected });
  }

  selectArticle(articleId: string): void {
    this.#selectArticle(articleId, true);
  }

  goBack(): void {
    if (this.#historyIndex <= 0) return;
    this.#historyIndex -= 1;
    this.#restoreHistory();
  }

  goForward(): void {
    if (this.#historyIndex >= this.#history.length - 1) return;
    this.#historyIndex += 1;
    this.#restoreHistory();
  }

  #restoreHistory(): void {
    const entry = this.#history[this.#historyIndex];
    const registry = this.#snapshot.registry;
    if (!entry || !registry) return;
    const selected = entry.type === "article"
      ? registry.resolveByArticleId(entry.value, this.#snapshot.locale)
      : registry.resolveByClassType(entry.value, this.#snapshot.locale);
    if (!selected) return;
    this.#set({
      selected,
      query: "",
      panel: "content",
      canGoBack: this.#historyIndex > 0,
      canGoForward: this.#historyIndex < this.#history.length - 1
    });
  }

  #selectArticle(articleId: string, recordHistory: boolean): void {
    const selected = this.#snapshot.registry?.resolveByArticleId(
      articleId,
      this.#snapshot.locale
    );
    if (!selected) return;
    const active = this.#history[this.#historyIndex];
    if (recordHistory && !(active?.type === "article" && active.value === articleId)) {
      this.#history = this.#history.slice(0, this.#historyIndex + 1);
      this.#history.push({ type: "article", value: articleId });
      this.#historyIndex = this.#history.length - 1;
    }
    this.#set({
      selected,
      query: "",
      panel: "content",
      canGoBack: this.#historyIndex > 0,
      canGoForward: this.#historyIndex < this.#history.length - 1
    });
  }

  selectClassType(classType: string): void {
    const registry = this.#snapshot.registry;
    if (!registry) {
      this.#pendingClassType = classType;
      return;
    }
    const selected = registry.resolveByClassType(classType, this.#snapshot.locale);
    const active = this.#history[this.#historyIndex];
    if (!(active?.type === "classType" && active.value === classType)) {
      this.#history = this.#history.slice(0, this.#historyIndex + 1);
      this.#history.push({ type: "classType", value: classType });
      this.#historyIndex = this.#history.length - 1;
    }
    this.#set({ selected, query: "", panel: "content", canGoBack: this.#historyIndex > 0, canGoForward: false });
  }

  async checkForUpdates(): Promise<void> {
    const updater = this.#updater;
    const catalogVersion = this.#snapshot.registry?.catalog.catalogVersion;
    if (
      !this.#snapshot.updatesEnabled ||
      !updater ||
      !catalogVersion ||
      this.#snapshot.update.status === "checking"
    ) return;
    this.#set({ update: { status: "checking" } });
    const generation = ++this.#updateCheckGeneration;
    this.#updateCheckController?.abort();
    const controller = new AbortController();
    this.#updateCheckController = controller;
    try {
      const result = await updater.check(catalogVersion, { signal: controller.signal });
      if (
        generation !== this.#updateCheckGeneration ||
        controller.signal.aborted ||
        !this.#snapshot.updatesEnabled
      ) return;
      const checkedAt = new Date().toISOString();
      this.#updateSchedule.markChecked();
      if (result.status === "available") {
        this.#updateCandidate = result.candidate;
        this.#set({
          update: {
            status: "available",
            version: result.candidate.catalog.catalogVersion,
            summary: result.candidate.manifest.changes.summary,
            artifactSize: signedCatalogSize(result.candidate),
            changes: boundedChanges(result.candidate),
            checkedAt
          }
        });
      } else {
        this.#updateCandidate = undefined;
        this.#set({ update: { status: "up-to-date", checkedAt } });
      }
    } catch (error) {
      if (
        generation !== this.#updateCheckGeneration ||
        controller.signal.aborted ||
        !this.#snapshot.updatesEnabled
      ) return;
      const checkedAt = new Date().toISOString();
      this.#updateSchedule.markChecked();
      this.#set({
        update: {
          status: "error",
          detail: error instanceof Error ? error.message : String(error),
          checkedAt
        }
      });
    } finally {
      if (generation === this.#updateCheckGeneration) this.#updateCheckController = undefined;
    }
  }

  async installAvailableUpdate(): Promise<void> {
    const updater = this.#updater;
    const candidate = this.#updateCandidate;
    if (!this.#snapshot.updatesEnabled || !updater || !candidate) return;
    const ru = this.#snapshot.locale === "ru";
    const record = await updater.apply(candidate, () => this.bridge.confirm(
      ru ? "Установить обновление каталога?" : "Install catalog update?",
      updateConfirmationMessage(candidate, ru)
    ));
    if (!record) return;
    const registry = new CatalogRegistry(record.catalog, this.#runtime);
    const current = this.#snapshot.selected;
    const selected = current
      ? registry.resolveByArticleId(current.article.manifest.articleId, this.#snapshot.locale) ??
        (current.article.manifest.runtimeIdentity
          ? registry.resolveByClassType(
              current.article.manifest.runtimeIdentity.classType,
              this.#snapshot.locale
            )
          : undefined)
      : undefined;
    this.#updateCandidate = undefined;
    this.#set({
      registry,
      selected,
      catalogSource: "signed-cache",
      update: { status: "up-to-date", checkedAt: new Date().toISOString() },
      canRollback: await this.#hasValidPrevious()
    });
  }

  setUpdatesEnabled(enabled: boolean): void {
    this.#updatePreference.setEnabled(enabled);
    this.#updateCandidate = undefined;
    if (!enabled) {
      this.#updateCheckGeneration += 1;
      this.#updateCheckController?.abort(new DOMException("Update checks disabled", "AbortError"));
      this.#updateCheckController = undefined;
      this.#updater = undefined;
      this.#set({
        updatesEnabled: false,
        update: { status: "disabled", detail: "Network update checks are disabled by the user." }
      });
      return;
    }
    const config = this.#effectiveUpdateConfig;
    const configured = updateConfigurationReady(config);
    this.#updater = configured ? new CatalogUpdater(config, this.#store) : undefined;
    this.#set({
      updatesEnabled: true,
      update: configured
        ? { status: "idle" }
        : {
            status: "disabled",
            detail: this.#updateConfig.enabled
              ? "Update verification configuration is incomplete."
              : "Release update URL and signing keys are not configured."
          }
    });
  }

  async rollbackCatalog(): Promise<void> {
    const previous = await this.#validPrevious();
    if (!previous) {
      this.#set({ canRollback: false });
      return;
    }
    const currentVersion = this.#snapshot.registry?.catalog.catalogVersion ?? "—";
    const previousVersion = previous.catalog.catalogVersion;
    const ru = this.#snapshot.locale === "ru";
    const accepted = await this.bridge.confirm(
      ru ? "Откатить каталог?" : "Roll back catalog?",
      ru
        ? `Версия ${currentVersion} будет заменена сохранённой версией ${previousVersion}.`
        : `Version ${currentVersion} will be replaced by saved version ${previousVersion}.`
    );
    if (!accepted) return;
    const restored = await this.#store.rollback();
    const catalog = parseStoredCatalog(restored?.catalog);
    if (!restored || !catalog) {
      this.#set({ canRollback: false });
      return;
    }
    const { registry, selected } = this.#rebuildCatalog(catalog);
    this.#updateCandidate = undefined;
    this.#set({
      registry,
      selected,
      catalogSource: restored.origin === "signed-update" ? "signed-cache" : "cache-fallback",
      canRollback: await this.#hasValidPrevious(),
      update: this.#snapshot.updatesEnabled && this.#updater
        ? { status: "idle" }
        : this.#snapshot.update
    });
  }

  resolveClassType(node: ComfyNodeLike): string | null {
    const comfyClass = exactNodeClassType(node);
    if (comfyClass) return comfyClass;
    if (typeof node.type !== "string") return null;
    const type = node.type.trim();
    const registry = this.#snapshot.registry;
    if (!registry || !type) return null;
    if (registry.runtimeDefinition(type) || registry.isUniqueCatalogClassType(type)) {
      return type;
    }
    return null;
  }

  async #doInitialise(): Promise<void> {
    this.#set({ phase: "loading", error: undefined });
    try {
      const loader = new CatalogLoader({
        store: this.#store,
        urls: this.#catalogUrls,
        fetch: this.#fetch
      });
      const [catalogResult, runtimeResult, versionResult] = await Promise.all([
        loader.load(),
        this.bridge
          .fetchObjectInfo()
          .then((runtime) => ({ runtime, warning: undefined }))
          .catch((error: unknown) => ({
            runtime: new Map(),
            warning: `/object_info: ${error instanceof Error ? error.message : String(error)}`
          })),
        this.bridge
          .fetchSystemVersions()
          .then((versions) => ({ versions, warning: undefined }))
          .catch((error: unknown) => ({
            versions: {} as { backend?: string; frontend?: string },
            warning: `/system_stats: ${error instanceof Error ? error.message : String(error)}`
          }))
      ]);
      const warnings = [...catalogResult.warnings];
      if (runtimeResult.warning) warnings.push(runtimeResult.warning);
      if (versionResult.warning) warnings.push(versionResult.warning);
      this.#runtime = runtimeResult.runtime;
      const registry = new CatalogRegistry(catalogResult.catalog, runtimeResult.runtime);
      if (registry.diagnostics.ambiguousClassTypes.length > 0) {
        warnings.push(
          `Ambiguous runtime identities: ${registry.diagnostics.ambiguousClassTypes.join(", ")}`
        );
      }
      const installedVersions = {
        comfyui: this.#updateConfig.installedVersions?.comfyui ?? versionResult.versions.backend,
        frontend: this.#updateConfig.installedVersions?.frontend ?? versionResult.versions.frontend
      };
      const effectiveUpdateConfig: CatalogUpdaterConfig = {
        ...this.#updateConfig,
        installedVersions: installedVersions.comfyui && installedVersions.frontend
          ? { comfyui: installedVersions.comfyui, frontend: installedVersions.frontend }
          : undefined
      };
      this.#effectiveUpdateConfig = effectiveUpdateConfig;
      const updateReady = updateConfigurationReady(effectiveUpdateConfig);
      const updatesEnabled = this.#updatePreference.isEnabled();
      if (updateReady && updatesEnabled) {
        this.#updater = new CatalogUpdater(effectiveUpdateConfig, this.#store);
      }
      this.#set({
        phase: "ready",
        registry,
        warnings,
        catalogSource: catalogResult.source,
        versions: {
          backend: installedVersions.comfyui,
          frontend: installedVersions.frontend
        },
        updatesEnabled,
        updateConfigured: updateReady,
        canRollback: await this.#hasValidPrevious(),
        update: !updatesEnabled
          ? { status: "disabled", detail: "Network update checks are disabled by the user." }
          : updateReady
            ? { status: "idle" }
            : {
              status: "disabled",
              detail: this.#updateConfig.enabled
                ? "Update verification is unavailable until URL, trusted keys, and installed versions are known."
                : "Release update URL and signing keys are not configured."
            }
      });
      this.#resolvePending();
      if (updateReady && updatesEnabled && this.#updateSchedule.isDue()) {
        void this.checkForUpdates();
      }
    } catch (error) {
      this.#set({
        phase: "error",
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }

  #rebuildCatalog(catalog: CatalogDocument): {
    registry: CatalogRegistry;
    selected: ResolvedArticle | undefined;
  } {
    const registry = new CatalogRegistry(catalog, this.#runtime);
    const current = this.#snapshot.selected;
    const selected = current
      ? registry.resolveByArticleId(current.article.manifest.articleId, this.#snapshot.locale) ??
        (current.article.manifest.runtimeIdentity
          ? registry.resolveByClassType(
              current.article.manifest.runtimeIdentity.classType,
              this.#snapshot.locale
            )
          : undefined)
      : undefined;
    return { registry, selected };
  }

  async #validPrevious(): Promise<StoredCatalogRecord | null> {
    try {
      const previous = await this.#store.getPrevious();
      if (!previous) return null;
      const catalog = parseStoredCatalog(previous.catalog);
      return catalog ? { ...previous, catalog } : null;
    } catch {
      return null;
    }
  }

  async #hasValidPrevious(): Promise<boolean> {
    return (await this.#validPrevious()) !== null;
  }

  #resolvePending(): void {
    const registry = this.#snapshot.registry;
    if (!registry) return;
    if (this.#pendingClassType) {
      const classType = this.#pendingClassType;
      this.#pendingClassType = undefined;
      this.selectClassType(classType);
      return;
    }
    if (!this.#snapshot.selected) {
      const first = registry.list(this.#snapshot.locale)[0];
      if (first) this.selectArticle(first.manifest.articleId);
    }
  }

  #set(patch: Partial<WizardSnapshot>): void {
    this.#snapshot = { ...this.#snapshot, ...patch };
    for (const listener of this.#listeners) listener();
  }
}

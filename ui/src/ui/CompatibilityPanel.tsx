import type { WizardController, WizardSnapshot } from "../app/controller";

function updateText(snapshot: WizardSnapshot, ru: boolean): string {
  const update = snapshot.update;
  if (update.status === "disabled") return ru ? `Отключены: ${update.detail}` : `Disabled: ${update.detail}`;
  if (update.status === "idle") return ru ? "Проверка ещё не выполнялась." : "No check has run yet.";
  if (update.status === "checking") return ru ? "Проверяем подписанный манифест…" : "Checking the signed manifest…";
  if (update.status === "up-to-date") return ru ? "Установлена актуальная версия." : "The catalog is up to date.";
  if (update.status === "available") {
    return ru ? `Доступна версия ${update.version}. ${update.summary}` : `Version ${update.version} is available. ${update.summary}`;
  }
  return ru ? `Проверка не удалась: ${update.detail}` : `Update check failed: ${update.detail}`;
}

function formatBytes(bytes: number, locale: string): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(bytes / 1024)} KiB`;
}

const changeLabels = {
  added: ["Добавлено", "Added"],
  updated: ["Обновлено", "Updated"],
  deprecated: ["Устарело", "Deprecated"],
  removed: ["Удалено", "Removed"]
} as const;

export function CompatibilityPanel({ controller }: { controller: WizardController }) {
  const snapshot = controller.getSnapshot();
  const catalog = snapshot.registry?.catalog;
  const selectedCompatibility = snapshot.selected?.article.manifest.compatibility;
  const ru = snapshot.locale === "ru";
  const canCheck = snapshot.update.status !== "disabled" && snapshot.update.status !== "checking";
  return (
    <section className="nw-compat" aria-labelledby="nw-compat-title">
      <div className="nw-kicker">{ru ? "Диагностика" : "Diagnostics"}</div>
      <h1 id="nw-compat-title">{ru ? "Совместимость и обновления" : "Compatibility and updates"}</h1>

      <h2>{ru ? "Установленные компоненты" : "Installed components"}</h2>
      <dl className="nw-compat-grid">
        <div><dt>Catalog</dt><dd>{catalog?.catalogVersion ?? "—"}</dd></div>
        <div><dt>Catalog schema</dt><dd>{catalog?.schemaVersion ?? "—"}</dd></div>
        <div><dt>ComfyUI backend</dt><dd>{snapshot.versions.backend ?? (ru ? "не определена" : "unknown")}</dd></div>
        <div><dt>ComfyUI frontend</dt><dd>{snapshot.versions.frontend ?? (ru ? "не определена" : "unknown")}</dd></div>
        <div><dt>{ru ? "Источник" : "Source"}</dt><dd>{snapshot.catalogSource ?? "—"}</dd></div>
        <div><dt>{ru ? "Собран" : "Generated"}</dt><dd>{catalog?.generatedAt || "—"}</dd></div>
      </dl>
      {catalog?.sourceUrl ? <p className="nw-source-url"><code>{catalog.sourceUrl}</code></p> : null}

      {selectedCompatibility ? (
        <>
          <h2>{ru ? "Текущая статья" : "Current article"}</h2>
          <dl className="nw-compat-grid">
            <div><dt>ComfyUI</dt><dd>{selectedCompatibility.comfyui ?? "—"}</dd></div>
            <div><dt>Frontend</dt><dd>{selectedCompatibility.frontend ?? "—"}</dd></div>
            <div><dt>Schema fingerprint</dt><dd><code>{selectedCompatibility.schemaFingerprint ?? "—"}</code></dd></div>
          </dl>
        </>
      ) : null}

      <h2>{ru ? "Подписанные обновления" : "Signed updates"}</h2>
      <label className="nw-update-toggle">
        <input
          type="checkbox"
          checked={snapshot.updatesEnabled}
          onChange={(event) => controller.setUpdatesEnabled(event.target.checked)}
        />
        <span>{ru ? "Разрешить сетевую проверку обновлений" : "Allow network update checks"}</span>
      </label>
      <div className="nw-update" data-status={snapshot.update.status}>
        <p>{updateText(snapshot, ru)}</p>
        {snapshot.update.status === "available" ? (
          <div className="nw-update-details">
            <p><b>{ru ? "Размер подписанного catalog.json" : "Signed catalog.json size"}:</b>{" "}
              {formatBytes(snapshot.update.artifactSize, snapshot.locale)}</p>
            {Object.entries(snapshot.update.changes).map(([kind, group]) => (
              group.total > 0 ? (
                <div className="nw-update-change" key={kind}>
                  <b>{changeLabels[kind as keyof typeof changeLabels][ru ? 0 : 1]} ({group.total})</b>
                  <ul>
                    {group.items.map((articleId: string) => <li key={articleId}><code>{articleId}</code></li>)}
                    {group.total > group.items.length ? (
                      <li>+{group.total - group.items.length} {ru ? "ещё" : "more"}</li>
                    ) : null}
                  </ul>
                </div>
              ) : null
            ))}
          </div>
        ) : null}
        <div className="nw-actions">
          {canCheck ? (
            <button className="nw-button" onClick={() => void controller.checkForUpdates()}>
              {ru ? "Проверить сейчас" : "Check now"}
            </button>
          ) : null}
          {snapshot.update.status === "available" ? (
            <button className="nw-button" onClick={() => void controller.installAvailableUpdate()}>
              {ru ? "Проверить подпись и установить" : "Verify and install"}
            </button>
          ) : null}
        </div>
      </div>
      <p className="nw-compat-note">
        {ru
          ? "Wizard никогда не устанавливает каталог без явного подтверждения. При пустом URL или keyring сетевой запрос не выполняется."
          : "Wizard never installs a catalog without explicit confirmation. No network request is made when the URL or keyring is empty."}
      </p>

      {snapshot.canRollback ? (
        <div className="nw-rollback">
          <button className="nw-button" onClick={() => void controller.rollbackCatalog()}>
            {ru ? "Откатить к предыдущему каталогу" : "Roll back to previous catalog"}
          </button>
          <span>{ru ? "Перед заменой потребуется подтверждение." : "Confirmation is required before replacement."}</span>
        </div>
      ) : null}

      <h2>{ru ? "Предупреждения" : "Warnings"}</h2>
      {snapshot.warnings.length > 0 ? (
        <ul className="nw-warning-list">
          {snapshot.warnings.map((warning, index) => <li key={`${index}:${warning}`}>{warning}</li>)}
        </ul>
      ) : <p className="nw-runtime-empty">{ru ? "Предупреждений нет." : "No warnings."}</p>}
    </section>
  );
}

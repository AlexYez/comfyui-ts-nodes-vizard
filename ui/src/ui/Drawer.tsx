import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore
} from "react";

import { catalogAssetBase } from "../catalog/locations";
import type { WizardController } from "../app/controller";
import type { CatalogArticle } from "../types/contracts";
import { ArtifactActions } from "./ArtifactActions";
import { MarkdownContent } from "./MarkdownContent";
import { RuntimeOverlay } from "./RuntimeOverlay";
import { CompatibilityPanel } from "./CompatibilityPanel";

const WIDTH_KEY = "nodes-wizard.drawer-width";
const SCROLL_KEY = "nodes-wizard.article-scroll.";

function ArticleRelations({ article, controller }: {
  article: CatalogArticle;
  controller: WizardController;
}) {
  const snapshot = controller.getSnapshot();
  const registry = snapshot.registry;
  const ru = snapshot.locale === "ru";
  if (!registry) return null;
  const groups = [
    {
      label: ru ? "Связанные ноды" : "Related nodes",
      ids: article.manifest.relations.related
    },
    {
      label: ru ? "Альтернативы" : "Alternatives",
      ids: article.manifest.relations.alternatives
    },
    {
      label: ru ? "Замена" : "Replacement",
      ids: article.manifest.relations.replacedBy
        ? [article.manifest.relations.replacedBy]
        : []
    }
  ].map((group) => ({
    ...group,
    articles: group.ids.flatMap((articleId) => {
      const target = registry.getByArticleId(articleId, snapshot.locale);
      return target ? [target] : [];
    })
  })).filter((group) => group.articles.length > 0);
  if (groups.length === 0) return null;

  return (
    <section className="nw-relations" aria-label={ru ? "Связи статьи" : "Article relations"}>
      <h2>{ru ? "Продолжить изучение" : "Continue learning"}</h2>
      {groups.map((group) => (
        <div className="nw-relation-group" key={group.label}>
          <h3>{group.label}</h3>
          <div className="nw-relation-links">
            {group.articles.map((target) => (
              <button
                className="nw-button"
                key={target.manifest.articleId}
                onClick={() => controller.selectArticle(target.manifest.articleId)}
              >
                {target.title}
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

function readWidth(): number {
  try {
    const stored = Number(localStorage.getItem(WIDTH_KEY));
    return Number.isFinite(stored) ? Math.min(900, Math.max(360, stored)) : 540;
  } catch {
    return 540;
  }
}

function ArticleView({ article, controller }: { article: CatalogArticle; controller: WizardController }) {
  const snapshot = controller.getSnapshot();
  const resolved = snapshot.selected;
  const identity = article.manifest.runtimeIdentity;
  const ru = snapshot.locale === "ru";
  const notice = resolved?.generated
    ? ru
      ? "Редакторская статья ещё не готова. Эта карточка собрана из текущего /object_info."
      : "This card was generated from the current /object_info; editorial content is pending."
    : resolved?.availability === "schema-changed"
      ? ru
        ? "Схема ноды изменилась после последней проверки статьи. Сверяйте параметры с текущей нодой."
        : "The node schema changed after this article was reviewed. Check parameters against the current node."
      : resolved?.availability === "not-installed"
        ? ru
          ? "Эта нода не обнаружена в текущей установке ComfyUI."
          : "This node was not detected in the current ComfyUI installation."
        : null;
  const nativeRenderer = useCallback(
    (markdown: string, baseUrl?: string) => controller.bridge.renderMarkdown(markdown, baseUrl),
    [controller]
  );

  return (
    <article className="nw-article">
      <div className="nw-kicker">
        {identity?.classType ?? article.manifest.kind}
      </div>
      <h1 className="nw-title">{article.title}</h1>
      <p className="nw-summary">{article.summary}</p>
      <div className="nw-badges">
        <span
          className="nw-badge"
          data-tone={article.manifest.status === "active" ? "success" : "warn"}
        >
          {article.manifest.status}
        </span>
        {identity?.pythonModule ? <span className="nw-badge">{identity.pythonModule}</span> : null}
        {article.tags.slice(0, 5).map((tag) => (
          <span className="nw-badge" key={tag}>{tag}</span>
        ))}
      </div>
      {notice ? <div className="nw-notice" role="status">{notice}</div> : null}
      {resolved?.runtime ? (
        <RuntimeOverlay runtime={resolved.runtime} locale={snapshot.locale} />
      ) : null}
      <MarkdownContent
        markdown={article.body}
        baseUrl={catalogAssetBase(snapshot.registry?.catalog.sourceUrl)}
        nativeRenderer={nativeRenderer}
      />
      <ArticleRelations article={article} controller={controller} />
      <ArtifactActions article={article} controller={controller} />
    </article>
  );
}

export function Drawer({ controller }: { controller: WizardController }) {
  const snapshot = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  );
  const [width, setWidth] = useState(readWidth);
  const closeButton = useRef<HTMLButtonElement>(null);
  const main = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  const ru = snapshot.locale === "ru";
  const results = useMemo(() => {
    if (!snapshot.registry) return [];
    if (snapshot.query.trim()) {
      return snapshot.registry.search(snapshot.query, snapshot.locale).map((result) => result.article);
    }
    return snapshot.registry.list(snapshot.locale);
  }, [snapshot.locale, snapshot.query, snapshot.registry]);
  const showingResults = snapshot.panel === "content" && (
    Boolean(snapshot.query.trim()) || !snapshot.selected
  );
  const inertProps = (!snapshot.open ? { inert: "" } : {}) as React.HTMLAttributes<HTMLElement>;

  useEffect(() => {
    if (snapshot.open && !wasOpen.current) {
      previousFocus.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      closeButton.current?.focus();
    } else if (!snapshot.open && wasOpen.current) {
      previousFocus.current?.focus({ preventScroll: true });
      previousFocus.current = null;
    }
    wasOpen.current = snapshot.open;
  }, [snapshot.open]);

  useEffect(() => {
    try { localStorage.setItem(WIDTH_KEY, String(width)); } catch { /* private mode */ }
  }, [width]);

  useEffect(() => {
    const element = main.current;
    const articleId = snapshot.selected?.article.manifest.articleId;
    if (!element || !articleId || showingResults || snapshot.panel !== "content") return;
    try { element.scrollTop = Number(sessionStorage.getItem(`${SCROLL_KEY}${articleId}`)) || 0; }
    catch { element.scrollTop = 0; }
    const remember = () => {
      try { sessionStorage.setItem(`${SCROLL_KEY}${articleId}`, String(element.scrollTop)); }
      catch { /* storage can be disabled */ }
    };
    element.addEventListener("scroll", remember, { passive: true });
    return () => {
      remember();
      element.removeEventListener("scroll", remember);
    };
  }, [showingResults, snapshot.panel, snapshot.selected?.article.manifest.articleId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && snapshot.open) controller.close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [controller, snapshot.open]);

  const startResize = (event: React.PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const onMove = (moveEvent: PointerEvent) => {
      const next = Math.min(900, Math.max(360, window.innerWidth - moveEvent.clientX));
      setWidth(next);
    };
    const onEnd = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onEnd);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onEnd, { once: true });
  };

  const selectResult = (article: CatalogArticle) => {
    if (article.manifest.articleId.startsWith("generated:")) {
      const classType = article.manifest.runtimeIdentity?.classType;
      if (classType) controller.selectClassType(classType);
      return;
    }
    controller.selectArticle(article.manifest.articleId);
  };

  return (
    <aside
      className="nw-shell"
      data-open={String(snapshot.open)}
      style={{ "--nw-width": `${width}px` } as React.CSSProperties}
      role="dialog"
      aria-modal="false"
      aria-label="TS Nodes Wizard"
      aria-hidden={!snapshot.open}
      {...inertProps}
    >
      <div className="nw-resizer" onPointerDown={startResize} aria-hidden="true" />
      <div className="nw-drawer">
        <header className="nw-header">
          <div className="nw-brand">
            <strong>TS Nodes Wizard</strong>
            <span>{ru ? "Справочник по нодам ComfyUI" : "ComfyUI node reference"}</span>
          </div>
          <div className="nw-history" aria-label={ru ? "История" : "History"}>
            <button className="nw-icon-button" disabled={!snapshot.canGoBack} onClick={() => controller.goBack()} aria-label={ru ? "Назад" : "Back"}>←</button>
            <button className="nw-icon-button" disabled={!snapshot.canGoForward} onClick={() => controller.goForward()} aria-label={ru ? "Вперёд" : "Forward"}>→</button>
          </div>
          {(snapshot.panel === "compatibility" || (snapshot.selected && !showingResults)) ? (
            <button className="nw-button" onClick={() => controller.showCatalog()}>
              {ru ? "Каталог" : "Catalog"}
            </button>
          ) : null}
          <button
            className="nw-icon-button"
            onClick={() => controller.showCompatibility()}
            aria-label={ru ? "Совместимость и обновления" : "Compatibility and updates"}
            title={ru ? "Совместимость и обновления" : "Compatibility and updates"}
          >
            ⚙
          </button>
          <button
            ref={closeButton}
            className="nw-icon-button"
            onClick={() => controller.close()}
            aria-label={ru ? "Закрыть" : "Close"}
          >
            ×
          </button>
        </header>
        <div className="nw-toolbar">
          <input
            className="nw-search"
            type="search"
            value={snapshot.query}
            placeholder={ru ? "Нода, понятие или системное имя…" : "Node, concept, or class type…"}
            onChange={(event) => controller.setQuery(event.target.value)}
            aria-label={ru ? "Поиск" : "Search"}
          />
          <select
            className="nw-locale"
            value={snapshot.locale === "ru" ? "ru" : "en"}
            onChange={(event) => controller.setLocale(event.target.value)}
            aria-label={ru ? "Язык" : "Language"}
          >
            <option value="ru">RU</option>
            <option value="en">EN</option>
          </select>
        </div>
        <main className="nw-main" ref={main}>
          {snapshot.phase === "loading" || snapshot.phase === "idle" ? (
            <div className="nw-state" role="status">{ru ? "Загружаем справочник…" : "Loading catalog…"}</div>
          ) : snapshot.phase === "error" ? (
            <div className="nw-state" role="alert">
              <div><strong>{ru ? "Справочник недоступен" : "Catalog unavailable"}</strong><br />{snapshot.error}</div>
            </div>
          ) : snapshot.panel === "compatibility" ? (
            <CompatibilityPanel controller={controller} />
          ) : showingResults ? (
            <ul className="nw-results">
              {results.map((article) => (
                <li key={`${article.manifest.articleId}:${article.manifest.locale}`}>
                  <button className="nw-result" onClick={() => selectResult(article)}>
                    <strong>{article.title}</strong>
                    <span>{article.manifest.runtimeIdentity?.classType ?? article.summary}</span>
                  </button>
                </li>
              ))}
              {results.length === 0 ? <li className="nw-state">{ru ? "Ничего не найдено" : "No results"}</li> : null}
            </ul>
          ) : snapshot.selected ? (
            <ArticleView article={snapshot.selected.article} controller={controller} />
          ) : null}
        </main>
        <footer className="nw-footer">
          <span>catalog {snapshot.registry?.catalog.catalogVersion ?? "—"}</span>
          <span>{snapshot.registry?.size ?? 0} / {snapshot.registry?.runtimeSize ?? 0} runtime</span>
        </footer>
      </div>
    </aside>
  );
}

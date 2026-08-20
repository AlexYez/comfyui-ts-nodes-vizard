export const wizardStyles = String.raw`
:host {
  --nw-bg: var(--comfy-menu-bg, var(--surface-card, #101216));
  --nw-panel: var(--comfy-input-bg, var(--surface-ground, #171a20));
  --nw-panel-2: var(--comfy-menu-secondary-bg, var(--surface-hover, #20242c));
  --nw-border: var(--border-color, var(--surface-border, rgba(255, 255, 255, .11)));
  --nw-text: var(--input-text, var(--text-color, #f3f4f6));
  --nw-muted: var(--descrip-text, var(--text-color-secondary, #a8adb8));
  --nw-accent: var(--p-primary-color, #8b7cf6);
  --nw-accent-2: var(--p-primary-300, #b7adff);
  --nw-warning: #f5b942;
  --nw-danger: #f87171;
  --nw-success: #5fd5a1;
  color-scheme: normal;
  font: 13px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
button, input, select { font: inherit; }
.nw-shell {
  position: fixed;
  inset: 0 0 0 auto;
  z-index: 100000;
  width: min(var(--nw-width, 540px), calc(100vw - 24px));
  transform: translateX(102%);
  transition: transform 180ms ease;
  pointer-events: none;
  color: var(--nw-text);
}
.nw-shell[data-open="true"] { transform: translateX(0); pointer-events: auto; }
.nw-resizer {
  position: absolute;
  inset: 0 auto 0 -6px;
  width: 12px;
  cursor: ew-resize;
  touch-action: none;
}
.nw-resizer::after {
  content: "";
  position: absolute;
  inset: 0 auto 0 5px;
  width: 1px;
  background: var(--nw-border);
}
.nw-drawer {
  height: 100%;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  background: var(--nw-bg);
  border-left: 1px solid var(--nw-border);
  box-shadow: -20px 0 60px rgba(0, 0, 0, .45);
}
.nw-header {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 58px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--nw-border);
}
.nw-brand { min-width: 0; flex: 1; }
.nw-brand strong { display: block; font-size: 14px; letter-spacing: .01em; }
.nw-brand span { color: var(--nw-muted); font-size: 11px; }
.nw-icon-button, .nw-button {
  border: 1px solid var(--nw-border);
  background: var(--nw-panel-2);
  color: var(--nw-text);
  border-radius: 8px;
  cursor: pointer;
}
.nw-icon-button { width: 34px; height: 34px; font-size: 18px; }
.nw-icon-button:disabled { opacity: .35; cursor: default; }
.nw-history { display: flex; gap: 4px; }
.nw-button { min-height: 34px; padding: 6px 11px; }
.nw-button:hover, .nw-icon-button:hover { border-color: var(--nw-accent); }
.nw-button:focus-visible, .nw-icon-button:focus-visible, input:focus-visible, select:focus-visible {
  outline: 2px solid var(--nw-accent);
  outline-offset: 2px;
}
.nw-toolbar { display: flex; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--nw-border); }
.nw-search {
  flex: 1;
  min-width: 0;
  height: 38px;
  border: 1px solid var(--nw-border);
  border-radius: 9px;
  background: var(--nw-panel);
  color: var(--nw-text);
  padding: 0 12px;
}
.nw-locale {
  border: 1px solid var(--nw-border);
  border-radius: 9px;
  background: var(--nw-panel);
  color: var(--nw-text);
  padding: 0 8px;
}
.nw-main { min-height: 0; overflow: auto; overscroll-behavior: contain; }
.nw-results { list-style: none; margin: 0; padding: 7px; }
.nw-result { width: 100%; text-align: left; padding: 10px; border: 0; border-radius: 9px; color: inherit; background: transparent; cursor: pointer; }
.nw-result:hover { background: var(--nw-panel-2); }
.nw-result strong { display: block; }
.nw-result span { display: block; color: var(--nw-muted); font-size: 12px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.nw-article { max-width: 820px; margin: 0 auto; padding: 24px 28px 52px; }
.nw-kicker { color: var(--nw-accent-2); font-size: 11px; text-transform: uppercase; letter-spacing: .1em; }
.nw-title { margin: 5px 0 7px; font-size: 25px; line-height: 1.2; }
.nw-summary { margin: 0 0 16px; color: var(--nw-muted); font-size: 14px; }
.nw-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 20px; }
.nw-badge { border: 1px solid var(--nw-border); border-radius: 999px; padding: 2px 8px; color: var(--nw-muted); font-size: 11px; }
.nw-badge[data-tone="warn"] { border-color: rgba(245,185,66,.5); color: var(--nw-warning); }
.nw-badge[data-tone="danger"] { border-color: rgba(248,113,113,.5); color: var(--nw-danger); }
.nw-badge[data-tone="success"] { border-color: rgba(95,213,161,.45); color: var(--nw-success); }
.nw-notice { border: 1px solid rgba(245,185,66,.35); background: rgba(245,185,66,.08); padding: 10px 12px; border-radius: 9px; margin: 0 0 18px; color: #f7d997; }
.nw-runtime { margin: 20px 0 26px; padding: 16px; border: 1px solid var(--nw-border); border-radius: 11px; background: var(--nw-panel); }
.nw-runtime-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.nw-runtime-heading h2 { margin: 2px 0 12px; font-size: 17px; }
.nw-runtime h3 { margin: 18px 0 7px; font-size: 13px; }
.nw-runtime-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 16px; margin: 0 0 12px; }
.nw-runtime-meta div { min-width: 0; }
.nw-runtime-meta dt { color: var(--nw-muted); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
.nw-runtime-meta dd { overflow-wrap: anywhere; margin: 1px 0 0; }
.nw-runtime-table-wrap { overflow: auto; }
.nw-runtime-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.nw-runtime-table th, .nw-runtime-table td { padding: 6px 7px; border: 1px solid var(--nw-border); text-align: left; vertical-align: top; }
.nw-runtime-table th { color: var(--nw-muted); font-weight: 600; }
.nw-constraint { display: block; white-space: nowrap; }
.nw-runtime-empty { color: var(--nw-muted); margin: 5px 0; }
.nw-runtime-hash { margin-top: 13px; color: var(--nw-muted); font-size: 10px; }
.nw-runtime-hash code { display: block; margin-top: 5px; overflow-wrap: anywhere; }
.nw-markdown { font-size: 14px; }
.nw-markdown h1 { display: none; }
.nw-markdown h2 { margin: 28px 0 9px; font-size: 18px; }
.nw-markdown h3 { margin: 22px 0 8px; font-size: 15px; }
.nw-markdown p { margin: 8px 0 13px; }
.nw-markdown a { color: var(--nw-accent-2); }
.nw-markdown code { padding: 1px 5px; border-radius: 5px; background: var(--nw-panel-2); }
.nw-markdown pre { overflow: auto; padding: 12px; border-radius: 9px; background: #0a0c0f; border: 1px solid var(--nw-border); }
.nw-markdown pre code { padding: 0; background: transparent; }
.nw-markdown table { width: 100%; border-collapse: collapse; overflow: auto; display: block; }
.nw-markdown th, .nw-markdown td { padding: 7px 9px; border: 1px solid var(--nw-border); text-align: left; }
.nw-markdown img, .nw-markdown video { max-width: 100%; border-radius: 8px; }
.nw-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--nw-border); }
.nw-relations { margin-top: 28px; padding-top: 18px; border-top: 1px solid var(--nw-border); }
.nw-relations h2 { margin: 0 0 12px; font-size: 18px; }
.nw-relation-group { margin-top: 12px; }
.nw-relation-group h3 { margin: 0 0 7px; color: var(--nw-muted); font-size: 12px; font-weight: 600; }
.nw-relation-links { display: flex; flex-wrap: wrap; gap: 8px; }
.nw-state { display: grid; place-items: center; min-height: 240px; padding: 30px; text-align: center; color: var(--nw-muted); }
.nw-footer { display: flex; justify-content: space-between; gap: 8px; padding: 7px 14px; color: var(--nw-muted); font-size: 10px; border-top: 1px solid var(--nw-border); background: var(--nw-panel); }
.nw-compat { max-width: 760px; margin: 0 auto; padding: 24px 28px 52px; }
.nw-compat h1 { margin: 5px 0 24px; font-size: 23px; }
.nw-compat h2 { margin: 24px 0 9px; font-size: 15px; }
.nw-compat-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin: 0; border: 1px solid var(--nw-border); background: var(--nw-border); border-radius: 9px; overflow: hidden; }
.nw-compat-grid div { min-width: 0; padding: 9px 10px; background: var(--nw-panel); }
.nw-compat-grid dt { color: var(--nw-muted); font-size: 10px; text-transform: uppercase; }
.nw-compat-grid dd { margin: 2px 0 0; overflow-wrap: anywhere; }
.nw-source-url { overflow-wrap: anywhere; color: var(--nw-muted); font-size: 10px; }
.nw-update { padding: 12px; border: 1px solid var(--nw-border); border-radius: 9px; background: var(--nw-panel); }
.nw-update p { margin: 0; }
.nw-update .nw-actions { margin-top: 10px; padding-top: 10px; }
.nw-update-toggle { display: flex; align-items: center; gap: 8px; margin: 0 0 9px; color: var(--nw-text); }
.nw-update-toggle input { accent-color: var(--nw-accent); }
.nw-update-details { display: grid; gap: 9px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--nw-border); }
.nw-update-change b { display: block; font-size: 11px; }
.nw-update-change ul { display: flex; flex-wrap: wrap; gap: 5px; list-style: none; margin: 5px 0 0; padding: 0; }
.nw-update-change li { max-width: 100%; padding: 2px 6px; border-radius: 5px; background: var(--nw-panel-2); overflow-wrap: anywhere; font-size: 10px; }
.nw-rollback { display: flex; align-items: center; gap: 10px; margin-top: 10px; color: var(--nw-muted); font-size: 10px; }
.nw-compat-note { color: var(--nw-muted); font-size: 11px; }
.nw-warning-list { margin: 0; padding-left: 20px; color: var(--nw-warning); overflow-wrap: anywhere; }
@media (max-width: 620px) {
  .nw-shell { width: 100vw; }
  .nw-resizer { display: none; }
  .nw-article { padding: 20px 18px 42px; }
  .nw-compat { padding: 20px 18px 42px; }
  .nw-compat-grid, .nw-runtime-meta { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) { .nw-shell { transition: none; } }
`;

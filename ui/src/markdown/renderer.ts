import DOMPurify from "dompurify";
import { marked } from "marked";

const SAFE_TAGS = [
  "a", "audio", "blockquote", "br", "code", "del", "em", "h1", "h2", "h3",
  "h4", "h5", "h6", "hr", "img", "li", "ol", "p", "pre", "source", "strong",
  "table", "tbody", "td", "th", "thead", "tr", "ul", "video"
];

const SAFE_ATTRIBUTES = [
  "alt", "aria-label", "controls", "height", "href", "loop", "muted", "poster",
  "preload", "rel", "src", "target", "title", "width"
];

export type NativeMarkdownRenderer = (
  markdown: string,
  baseUrl?: string
) => string | undefined;

function isLocalMediaUrl(raw: string, baseUrl: string | undefined): boolean {
  try {
    const url = new URL(raw, baseUrl ?? document.baseURI);
    if (url.protocol === "blob:") return true;
    if (!baseUrl || url.origin !== window.location.origin) return false;
    const catalogBase = new URL(baseUrl, document.baseURI);
    const basePath = catalogBase.pathname.endsWith("/")
      ? catalogBase.pathname
      : `${catalogBase.pathname}/`;
    return catalogBase.origin === window.location.origin && url.pathname.startsWith(basePath);
  } catch {
    return false;
  }
}

function hardenDocument(html: string, baseUrl: string | undefined): string {
  const template = document.createElement("template");
  template.innerHTML = html;
  for (const link of template.content.querySelectorAll<HTMLAnchorElement>("a[href]")) {
    const raw = link.getAttribute("href") ?? "";
    if (/^https?:/i.test(raw)) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
  }
  // Media is passive UI but active networking: never let an article beacon a remote host.
  for (const media of template.content.querySelectorAll<HTMLElement>(
    "img[src], audio[src], video[src], source[src], track[src]"
  )) {
    const raw = media.getAttribute("src") ?? "";
    if (!isLocalMediaUrl(raw, baseUrl)) media.removeAttribute("src");
  }
  for (const video of template.content.querySelectorAll<HTMLElement>("video[poster]")) {
    const raw = video.getAttribute("poster") ?? "";
    if (!isLocalMediaUrl(raw, baseUrl)) video.removeAttribute("poster");
  }
  return template.innerHTML;
}

export async function renderSafeMarkdown(
  markdown: string,
  baseUrl: string | undefined,
  nativeRenderer?: NativeMarkdownRenderer
): Promise<string> {
  let html: string | undefined;
  try {
    html = nativeRenderer?.(markdown, baseUrl);
  } catch {
    html = undefined;
  }
  if (!html) {
    const rendered = marked.parse(markdown, { gfm: true, async: false });
    html = typeof rendered === "string" ? rendered : await rendered;
  }
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: SAFE_TAGS,
    ALLOWED_ATTR: SAFE_ATTRIBUTES,
    ALLOW_DATA_ATTR: false
  });
  return hardenDocument(clean, baseUrl);
}

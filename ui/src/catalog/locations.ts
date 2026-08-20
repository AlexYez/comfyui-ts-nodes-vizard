export const PRIMARY_CATALOG_URL =
  "/extensions/comfyui-ts-nodes-vizard/data/catalog.json";

function normaliseUrl(url: URL): string {
  return `${url.pathname}${url.search}`;
}

export function detectExtensionBase(
  documentValue: Document = document,
  locationValue: Location = window.location
): string | null {
  const current = documentValue.currentScript as HTMLScriptElement | null;
  const scripts = [
    ...(current?.src ? [current] : []),
    ...Array.from(documentValue.querySelectorAll<HTMLScriptElement>("script[src]"))
  ];

  for (const script of scripts.reverse()) {
    let url: URL;
    try {
      url = new URL(script.src, locationValue.href);
    } catch {
      continue;
    }
    if (url.origin !== locationValue.origin) continue;
    const match = url.pathname.match(/^(.*\/extensions\/[^/]+)(?:\/|$)/);
    if (match?.[1]) return match[1].replace(/\/$/, "");
  }
  return null;
}

export function catalogUrlCandidates(
  documentValue: Document = document,
  locationValue: Location = window.location
): string[] {
  const candidates = [PRIMARY_CATALOG_URL];
  const detectedBase = detectExtensionBase(documentValue, locationValue);
  if (detectedBase) {
    candidates.push(`${detectedBase}/data/catalog.json`);
  }
  return [...new Set(candidates.map((url) => normaliseUrl(new URL(url, locationValue.href))))];
}

export function catalogAssetBase(sourceUrl: string | undefined): string | undefined {
  if (!sourceUrl) return undefined;
  try {
    return new URL(".", new URL(sourceUrl, window.location.href)).href;
  } catch {
    return undefined;
  }
}

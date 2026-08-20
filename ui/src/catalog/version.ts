function tokens(version: string): Array<number | string> {
  return version
    .trim()
    .replace(/^v/i, "")
    .split(/[.+_-]/)
    .filter(Boolean)
    .map((token) => (/^\d+$/.test(token) ? Number(token) : token.toLowerCase()));
}

export function compareCatalogVersions(left: string, right: string): number {
  const leftTokens = tokens(left);
  const rightTokens = tokens(right);
  const count = Math.max(leftTokens.length, rightTokens.length);
  for (let index = 0; index < count; index += 1) {
    const a = leftTokens[index] ?? 0;
    const b = rightTokens[index] ?? 0;
    if (a === b) continue;
    if (typeof a === "number" && typeof b === "number") return a > b ? 1 : -1;
    if (typeof a === "number") return 1;
    if (typeof b === "number") return -1;
    return a.localeCompare(b);
  }
  return 0;
}


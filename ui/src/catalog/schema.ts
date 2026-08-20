import { z } from "zod";

import type {
  ArticleKind,
  ArticleManifest,
  ArticleRelations,
  ArticleStatus,
  CatalogArticle,
  CatalogDocument,
  LocaleCode,
  RuntimeIdentity
} from "../types/contracts";

const rawArticleSchema = z
  .object({
    manifest: z.record(z.unknown()).optional().default({}),
    title: z.string().optional().default(""),
    summary: z.string().optional().default(""),
    tags: z.array(z.string()).optional().default([]),
    concepts: z.array(z.string()).optional().default([]),
    body: z.string().optional().default(""),
    recipeData: z.unknown().optional(),
    workflowData: z.unknown().optional()
  })
  .passthrough();

const rawCatalogSchema = z
  .object({
    schemaVersion: z.union([z.string(), z.number()]).optional().default("1"),
    catalogVersion: z.union([z.string(), z.number()]).optional().default("0"),
    locale: z.string().optional().default("ru"),
    generatedAt: z.string().optional().default(""),
    articles: z.array(rawArticleSchema).optional().default([])
  })
  .passthrough();

const storedRuntimeIdentitySchema = z.object({
  classType: z.string().min(1),
  kind: z.enum(["server", "frontend"]),
  aliases: z.array(z.string()),
  packageId: z.string().optional(),
  pythonModule: z.string().optional()
}).passthrough();

const storedArticleSchema = z.object({
  manifest: z.object({
    articleId: z.string().min(1),
    kind: z.enum(["core", "custom", "virtual", "concept"]),
    locale: z.string().min(1),
    runtimeIdentity: storedRuntimeIdentitySchema.optional(),
    searchAliases: z.array(z.string()),
    status: z.enum(["active", "deprecated", "experimental", "removed", "stale", "draft"]),
    compatibility: z.record(z.unknown()),
    relations: z.object({
      related: z.array(z.string()),
      alternatives: z.array(z.string()),
      replacedBy: z.string().optional()
    }),
    assets: z.array(z.unknown()),
    editorial: z.record(z.unknown()),
    sources: z.array(z.unknown())
  }).passthrough(),
  title: z.string(),
  summary: z.string(),
  tags: z.array(z.string()),
  concepts: z.array(z.string()),
  body: z.string(),
  recipeData: z.unknown().optional(),
  workflowData: z.unknown().optional()
}).passthrough();

const storedCatalogSchema = z.object({
  schemaVersion: z.literal("1.0"),
  catalogVersion: z.string().regex(/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/),
  locale: z.string().min(1),
  generatedAt: z.string(),
  articles: z.array(storedArticleSchema).min(1).max(20_000),
  sourceUrl: z.string().optional()
}).passthrough();

const articleKinds = new Set<ArticleKind>([
  "core",
  "custom",
  "virtual",
  "concept"
]);
const articleStatuses = new Set<ArticleStatus>([
  "active",
  "deprecated",
  "experimental",
  "removed",
  "stale",
  "draft"
]);

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(...values: unknown[]): string | undefined {
  return values.find(
    (value): value is string => typeof value === "string" && value.trim().length > 0
  )?.trim();
}

function stringArray(value: unknown): string[] {
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item): item is string => typeof item === "string"))];
}

function normaliseRelations(value: unknown): ArticleRelations {
  if (Array.isArray(value)) {
    const related: string[] = [];
    const alternatives: string[] = [];
    let replacedBy: string | undefined;
    for (const item of value) {
      const relation = record(item);
      const type = stringValue(relation.type);
      const articleId = stringValue(relation.articleId, relation.article_id);
      if (!articleId) continue;
      if (type === "related") related.push(articleId);
      if (type === "alternative") alternatives.push(articleId);
      if (type === "replacedBy") replacedBy = articleId;
    }
    return {
      related: [...new Set(related)],
      alternatives: [...new Set(alternatives)],
      replacedBy
    };
  }
  const source = record(value);
  return {
    related: stringArray(source.related),
    alternatives: stringArray(source.alternatives),
    replacedBy: stringValue(source.replacedBy, source.replaced_by)
  };
}

function normaliseIdentity(manifest: Record<string, unknown>): RuntimeIdentity | undefined {
  const identity = record(
    manifest.runtimeIdentity ?? manifest.runtime_identity ?? manifest.node
  );
  const classType = stringValue(
    identity.classType,
    identity.class_type,
    identity.nodeId,
    identity.node_id,
    manifest.classType,
    manifest.class_type,
    manifest.nodeType,
    manifest.node_type
  );
  if (!classType) return undefined;
  const origin = stringValue(identity.kind, identity.origin, manifest.origin);
  const kind = origin === "frontend" ? "frontend" : "server";

  return {
    classType,
    kind,
    aliases: stringArray(identity.aliases ?? manifest.aliases).filter(
      (alias) => alias !== classType
    ),
    packageId: stringValue(
      identity.packageId,
      identity.package_id,
      manifest.packageId,
      manifest.package_id
    ),
    pythonModule: stringValue(
      identity.pythonModule,
      identity.python_module,
      manifest.pythonModule,
      manifest.python_module
    )
  };
}

function normaliseManifest(
  rawManifest: Record<string, unknown>,
  catalogLocale: LocaleCode,
  articleIndex: number
): ArticleManifest {
  const runtimeIdentity = normaliseIdentity(rawManifest);
  const articleId =
    stringValue(rawManifest.articleId, rawManifest.article_id, rawManifest.id) ??
    runtimeIdentity?.classType ??
    `article-${articleIndex + 1}`;
  const compatibility = record(rawManifest.compatibility);
  const editorial = record(rawManifest.editorial);
  const kindValue = stringValue(rawManifest.kind);
  const statusValue = stringValue(rawManifest.status);

  return {
    articleId,
    kind: articleKinds.has(kindValue as ArticleKind)
      ? (kindValue as ArticleKind)
      : "core",
    locale: (stringValue(rawManifest.locale) ?? catalogLocale) as LocaleCode,
    runtimeIdentity,
    searchAliases: stringArray(
      rawManifest.searchAliases ?? rawManifest.search_aliases
    ),
    status: articleStatuses.has(statusValue as ArticleStatus)
      ? (statusValue as ArticleStatus)
      : "active",
    compatibility: {
      comfyui: stringValue(compatibility.comfyui),
      frontend: stringValue(compatibility.frontend),
      since: stringValue(compatibility.since),
      until: stringValue(compatibility.until),
      schemaFingerprint: stringValue(
        compatibility.schemaFingerprint,
        compatibility.schema_fingerprint
      )
    },
    relations: normaliseRelations(rawManifest.relations),
    assets: Array.isArray(rawManifest.assets) ? rawManifest.assets : [],
    editorial: {
      reviewedAt: stringValue(editorial.reviewedAt, editorial.reviewed_at),
      schemaHash: stringValue(editorial.schemaHash, editorial.schema_hash),
      author: stringValue(editorial.author)
    },
    sources: Array.isArray(rawManifest.sources) ? rawManifest.sources : []
  };
}

export function decodeCatalog(input: unknown, sourceUrl?: string): CatalogDocument {
  const raw = rawCatalogSchema.parse(input);
  const locale = raw.locale as LocaleCode;
  const articles: CatalogArticle[] = raw.articles.map((article, index) => ({
    manifest: normaliseManifest(article.manifest, locale, index),
    title: article.title.trim(),
    summary: article.summary.trim(),
    tags: [...new Set(article.tags.map((tag) => tag.trim()).filter(Boolean))],
    concepts: [
      ...new Set(article.concepts.map((concept) => concept.trim()).filter(Boolean))
    ],
    body: article.body,
    ...(article.recipeData === undefined ? {} : { recipeData: article.recipeData }),
    ...(article.workflowData === undefined ? {} : { workflowData: article.workflowData })
  }));

  return {
    schemaVersion: String(raw.schemaVersion),
    catalogVersion: String(raw.catalogVersion),
    locale,
    generatedAt: raw.generatedAt,
    articles,
    sourceUrl
  };
}

/** Validates structured-clone data read from IndexedDB before version selection. */
export function parseStoredCatalog(input: unknown): CatalogDocument | null {
  const result = storedCatalogSchema.safeParse(input);
  if (!result.success) return null;
  const articleKeys = new Set<string>();
  const identityKeys = new Set<string>();
  const articleIds = new Set(result.data.articles.map((article) => article.manifest.articleId));
  for (const article of result.data.articles) {
    const articleKey = `${article.manifest.articleId}\u0000${article.manifest.locale}`;
    if (articleKeys.has(articleKey)) return null;
    articleKeys.add(articleKey);
    const identity = article.manifest.runtimeIdentity;
    if (identity) {
      const identityKey = [
        article.manifest.locale,
        identity.kind,
        identity.packageId ?? "",
        identity.pythonModule ?? "",
        identity.classType
      ].join("\u001f");
      if (identityKeys.has(identityKey)) return null;
      identityKeys.add(identityKey);
    }
    const relations = [
      ...article.manifest.relations.related,
      ...article.manifest.relations.alternatives,
      ...(article.manifest.relations.replacedBy ? [article.manifest.relations.replacedBy] : [])
    ];
    if (relations.some((articleId) => !articleIds.has(articleId))) return null;
  }
  return result.data as CatalogDocument;
}

export function emptyCatalog(locale: LocaleCode = "ru"): CatalogDocument {
  return {
    schemaVersion: "1",
    catalogVersion: "unavailable",
    locale,
    generatedAt: "",
    articles: []
  };
}

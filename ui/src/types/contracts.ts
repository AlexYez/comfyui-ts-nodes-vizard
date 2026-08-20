export type LocaleCode = "ru" | "en" | (string & {});

export type ArticleKind = "core" | "custom" | "virtual" | "concept";

export type ArticleStatus =
  | "active"
  | "deprecated"
  | "experimental"
  | "removed"
  | "stale"
  | "draft";

export type RuntimeKind = "server" | "frontend";

export interface NodeKey {
  /** Exact ComfyUI execution identity (`class_type` / NODE_CLASS_MAPPINGS key). */
  classType: string;
  packageId?: string;
  pythonModule?: string;
  kind: RuntimeKind;
}

export interface RuntimeIdentity extends NodeKey {
  /** Explicit historical identities. These are never inferred from display names. */
  aliases: string[];
}

export interface ArticleCompatibility {
  comfyui?: string;
  frontend?: string;
  since?: string;
  until?: string;
  schemaFingerprint?: string;
}

export interface ArticleRelations {
  related: string[];
  alternatives: string[];
  replacedBy?: string;
}

export interface ArticleEditorial {
  reviewedAt?: string;
  schemaHash?: string;
  author?: string;
}

export interface ArticleManifest {
  articleId: string;
  kind: ArticleKind;
  locale: LocaleCode;
  runtimeIdentity?: RuntimeIdentity;
  searchAliases: string[];
  status: ArticleStatus;
  compatibility: ArticleCompatibility;
  relations: ArticleRelations;
  assets: unknown[];
  editorial: ArticleEditorial;
  sources: unknown[];
}

export interface CatalogArticle {
  manifest: ArticleManifest;
  title: string;
  summary: string;
  tags: string[];
  concepts: string[];
  body: string;
  recipeData?: unknown;
  workflowData?: unknown;
}

export interface CatalogDocument {
  schemaVersion: string;
  catalogVersion: string;
  locale: LocaleCode;
  generatedAt: string;
  articles: CatalogArticle[];
  /** Runtime-only origin, intentionally omitted from the compiled JSON. */
  sourceUrl?: string;
}

export interface RuntimePort {
  name: string;
  type: string;
  optional: boolean;
  isList?: boolean;
  tooltip?: string;
  constraints?: Readonly<Record<string, unknown>>;
}

export interface RuntimeNodeDefinition extends NodeKey {
  displayName: string;
  description: string;
  category: string;
  pythonModule?: string;
  deprecated: boolean;
  experimental: boolean;
  apiNode: boolean;
  inputs: RuntimePort[];
  outputs: RuntimePort[];
  schemaHash: string;
  raw: Readonly<Record<string, unknown>>;
}

export type RuntimeNodeMap = ReadonlyMap<string, RuntimeNodeDefinition>;

export type ArticleAvailability =
  | "available"
  | "schema-changed"
  | "not-installed"
  | "generated";

export interface ResolvedArticle {
  article: CatalogArticle;
  runtime?: RuntimeNodeDefinition;
  availability: ArticleAvailability;
  generated: boolean;
}

export interface CatalogDiagnostics {
  duplicateArticleIds: string[];
  duplicateRuntimeIdentities: string[];
  aliasConflicts: string[];
  ambiguousClassTypes: string[];
}

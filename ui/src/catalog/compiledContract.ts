import compiledSchemaText from "../../../content/schemas/compiled-catalog.schema.v1.json?raw";

type JsonObject = Record<string, unknown>;

const compiledSchema = JSON.parse(compiledSchemaText) as JsonObject;

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function matchesType(value: unknown, expected: string): boolean {
  if (expected === "null") return value === null;
  if (expected === "boolean") return typeof value === "boolean";
  if (expected === "integer") return typeof value === "number" && Number.isInteger(value);
  if (expected === "number") return typeof value === "number" && Number.isFinite(value);
  if (expected === "string") return typeof value === "string";
  if (expected === "array") return Array.isArray(value);
  if (expected === "object") return isObject(value);
  return false;
}

function isDate(value: string): boolean {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match?.[1] || !match[2] || !match[3]) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day;
}

function isDateTime(value: string): boolean {
  return /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
}

function resolveReference(reference: string): JsonObject {
  if (!reference.startsWith("#/")) {
    throw new Error(`Unsupported non-local compiled-catalog schema reference: ${reference}`);
  }
  let current: unknown = compiledSchema;
  for (const rawToken of reference.slice(2).split("/")) {
    const token = rawToken.replaceAll("~1", "/").replaceAll("~0", "~");
    if (!isObject(current) || !(token in current)) {
      throw new Error(`Unresolved compiled-catalog schema reference: ${reference}`);
    }
    current = current[token];
  }
  if (!isObject(current)) {
    throw new Error(`Compiled-catalog schema reference is not an object: ${reference}`);
  }
  return current;
}

/** Browser-side validator for the exact JSON Schema subset used by catalog.py. */
export function compiledCatalogSchemaErrors(input: unknown): string[] {
  const errors: string[] = [];

  const visit = (value: unknown, rule: JsonObject, path: string): void => {
    if (typeof rule.$ref === "string") {
      visit(value, resolveReference(rule.$ref), path);
      return;
    }
    if (Object.hasOwn(rule, "const") && value !== rule.const) {
      errors.push(`${path}: unexpected constant value`);
    }
    if (Array.isArray(rule.enum) && !rule.enum.includes(value)) {
      errors.push(`${path}: value is outside the allowed enum`);
    }

    const declared = rule.type;
    const expected = typeof declared === "string" ? [declared] : declared;
    if (
      Array.isArray(expected) &&
      !expected.some((type) => typeof type === "string" && matchesType(value, type))
    ) {
      errors.push(`${path}: unexpected JSON type`);
      return;
    }

    if (typeof value === "string") {
      if (typeof rule.minLength === "number" && value.length < rule.minLength) {
        errors.push(`${path}: string is too short`);
      }
      if (typeof rule.maxLength === "number" && value.length > rule.maxLength) {
        errors.push(`${path}: string is too long`);
      }
      if (typeof rule.pattern === "string" && !new RegExp(rule.pattern).test(value)) {
        errors.push(`${path}: string does not match the required pattern`);
      }
      if (rule.format === "date" && !isDate(value)) errors.push(`${path}: invalid date`);
      if (rule.format === "date-time" && !isDateTime(value)) {
        errors.push(`${path}: invalid timezone-aware date-time`);
      }
    }

    if (Array.isArray(value)) {
      if (typeof rule.minItems === "number" && value.length < rule.minItems) {
        errors.push(`${path}: array has too few items`);
      }
      if (typeof rule.maxItems === "number" && value.length > rule.maxItems) {
        errors.push(`${path}: array has too many items`);
      }
      if (isObject(rule.items)) {
        value.forEach((item, index) => visit(item, rule.items as JsonObject, `${path}[${index}]`));
      }
    }

    if (isObject(value)) {
      if (Array.isArray(rule.required)) {
        for (const key of rule.required) {
          if (typeof key === "string" && !Object.hasOwn(value, key)) {
            errors.push(`${path}: missing required property ${key}`);
          }
        }
      }
      const properties = isObject(rule.properties) ? rule.properties : {};
      for (const [key, child] of Object.entries(value)) {
        const childRule = properties[key];
        if (isObject(childRule)) {
          visit(child, childRule, `${path}.${key}`);
        } else if (rule.additionalProperties === false) {
          errors.push(`${path}: additional property ${key} is not allowed`);
        } else if (isObject(rule.additionalProperties)) {
          visit(child, rule.additionalProperties, `${path}.${key}`);
        }
      }
    }
  };

  visit(input, compiledSchema, "$catalog");
  return errors;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function nullableText(value: unknown): string {
  return value === null || value === undefined ? "" : text(value);
}

/** JSON Schema plus cross-record invariants that JSON Schema cannot express. */
export function assertCompiledCatalog(input: unknown): asserts input is JsonObject {
  const schemaErrors = compiledCatalogSchemaErrors(input);
  if (schemaErrors.length > 0) {
    throw new Error(`Catalog violates compiled schema: ${schemaErrors.slice(0, 8).join("; ")}`);
  }
  if (!isObject(input) || !Array.isArray(input.articles)) {
    throw new Error("Catalog has no article collection");
  }
  if (input.articles.length > 20_000) throw new Error("Catalog contains too many articles");

  const articleKeys = new Set<string>();
  const articleIds = new Set<string>();
  const identityKeys = new Set<string>();
  const canonicalIdentities = new Set<string>();
  const aliasIdentities: Array<{ key: string; articleId: string }> = [];
  const relationTargets: string[] = [];
  let bodyBytes = 0;

  for (const rawArticle of input.articles) {
    if (!isObject(rawArticle) || !isObject(rawArticle.manifest)) continue;
    const manifest = rawArticle.manifest;
    const articleId = text(manifest.articleId);
    const locale = text(manifest.locale);
    const articleKey = `${articleId}\u0000${locale}`;
    if (articleKeys.has(articleKey)) throw new Error(`Duplicate catalog article: ${articleId}`);
    articleKeys.add(articleKey);
    articleIds.add(articleId);

    const encodedBody = new TextEncoder().encode(text(rawArticle.body)).byteLength;
    if (encodedBody > 2 * 1024 * 1024) throw new Error(`${articleId}.body is too large`);
    bodyBytes += encodedBody;
    if (bodyBytes > 32 * 1024 * 1024) throw new Error("Catalog article bodies are too large");

    const node = isObject(manifest.node) ? manifest.node : {};
    const identity = isObject(manifest.runtimeIdentity) ? manifest.runtimeIdentity : {};
    const nodeKind = text(node.kind);
    const origin = text(identity.origin);
    if (
      text(node.nodeId) !== text(identity.classType) ||
      nodeKind !== origin ||
      nullableText(node.packageId) !== nullableText(identity.packageId) ||
      nullableText(node.pythonModule) !== nullableText(identity.pythonModule)
    ) {
      throw new Error(`${articleId} has inconsistent node/runtime identity`);
    }
    const provenance = [
      locale,
      origin,
      nullableText(identity.packageId),
      nullableText(identity.pythonModule)
    ].join("\u001f");
    const identityKey = `${provenance}\u001f${text(identity.classType)}`;
    if (identityKeys.has(identityKey)) {
      throw new Error(`Duplicate runtime identity: ${text(identity.classType)}`);
    }
    identityKeys.add(identityKey);
    canonicalIdentities.add(identityKey);
    if (Array.isArray(identity.aliases)) {
      for (const alias of identity.aliases) {
        aliasIdentities.push({ key: `${provenance}\u001f${text(alias)}`, articleId });
      }
    }

    const editorial = isObject(manifest.editorial) ? manifest.editorial : {};
    if (manifest.editorialState !== editorial.state) {
      throw new Error(`${articleId} has inconsistent editorial state`);
    }
    if (Array.isArray(manifest.relations)) {
      for (const relation of manifest.relations) {
        if (isObject(relation)) relationTargets.push(text(relation.articleId));
      }
    }
  }

  const aliases = new Set<string>();
  for (const alias of aliasIdentities) {
    if (canonicalIdentities.has(alias.key)) {
      throw new Error(`${alias.articleId} alias collides with a canonical runtime identity`);
    }
    if (aliases.has(alias.key)) throw new Error("Duplicate runtime alias identity");
    aliases.add(alias.key);
  }
  for (const target of relationTargets) {
    if (!articleIds.has(target)) throw new Error(`Relation targets an unknown article: ${target}`);
  }
}

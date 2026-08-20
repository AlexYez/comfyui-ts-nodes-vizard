import { verifyAsync } from "@noble/ed25519";
import { z } from "zod";

import type { CatalogDocument } from "../types/contracts";
import { canonicalJson } from "../runtime/objectInfo";
import { assertCompiledCatalog } from "./compiledContract";
import { decodeCatalog } from "./schema";
import type { CatalogStore, StoredCatalogRecord } from "./storage";
import { compareCatalogVersions } from "./version";

const SHA256 = /^[a-f0-9]{64}$/;
const SAFE_ARTIFACT_PATH = /^(?:[A-Za-z0-9._-]+\/)*catalog\.json$/;

const artifactSchema = z.object({
  path: z.string().min(1),
  sha256: z.string().regex(SHA256),
  size: z.number().int().nonnegative(),
  url: z.string().url(),
  contentType: z.string().min(3)
}).strict();

const signatureSchema = z.object({
  algorithm: z.literal("Ed25519"),
  keyId: z.string().min(1),
  publicKey: z.string().min(1),
  value: z.string().min(1)
}).strict();

const updateManifestSchema = z.object({
  $schema: z.string(),
  schemaVersion: z.literal("1.0"),
  catalogVersion: z.string().regex(/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/),
  publishedAt: z.string(),
  canonicalization: z.literal("comfy-nodes-wizard-json-v1"),
  signatureScope: z.literal("top-level-manifest-excluding-signature"),
  compatibility: z.object({
    comfyui: z.string(),
    frontend: z.string()
  }).strict(),
  inventory: z.object({
    source: z.string(),
    comfyuiVersion: z.string(),
    frontendVersion: z.string().optional(),
    capturedAt: z.string()
  }).strict(),
  artifacts: z.array(artifactSchema).min(1).max(16),
  changes: z.object({
    summary: z.string().min(1).max(500),
    added: z.array(z.string()).max(10_000),
    updated: z.array(z.string()).max(10_000),
    deprecated: z.array(z.string()).max(10_000),
    removed: z.array(z.string()).max(10_000)
  }).strict(),
  signature: signatureSchema.nullable()
}).strict();

export type SignedUpdateManifest = z.infer<typeof updateManifestSchema>;

export interface CatalogUpdaterConfig {
  /** Must remain false until release keys and an HTTPS endpoint are provisioned. */
  enabled: boolean;
  manifestUrl: string;
  /** Trusted keys keyed by keyId, encoded as base64url or 64-char hex. */
  publicKeys: Readonly<Record<string, string>>;
  /** Required when enabled, so compatibility is checked before the candidate is offered. */
  installedVersions?: { comfyui: string; frontend: string };
  /** Empty means the manifest origin only. */
  allowedOrigins?: readonly string[];
  maxManifestBytes?: number;
  maxCatalogBytes?: number;
  /** Per complete manifest+artifact check. Defaults to 15 seconds. */
  timeoutMs?: number;
  fetch?: typeof globalThis.fetch;
}

export const DISABLED_UPDATE_CONFIG: CatalogUpdaterConfig = Object.freeze({
  enabled: false,
  manifestUrl: "",
  publicKeys: Object.freeze({})
});

export interface CatalogUpdateCandidate {
  readonly catalog: CatalogDocument;
  readonly manifest: SignedUpdateManifest;
  readonly keyId: string;
  readonly sha256: string;
  readonly sourceUrl: string;
}

export type CatalogUpdateCheck =
  | { status: "disabled" }
  | { status: "up-to-date"; catalogVersion: string }
  | { status: "available"; candidate: CatalogUpdateCandidate };

export type ConfirmCatalogUpdate = (
  candidate: CatalogUpdateCandidate
) => boolean | Promise<boolean>;

function decodeBytes(value: string): Uint8Array {
  if (/^[a-f0-9]+$/i.test(value) && value.length % 2 === 0) {
    return Uint8Array.from(
      value.match(/.{2}/g)?.map((pair) => Number.parseInt(pair, 16)) ?? []
    );
  }
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error("Invalid base64url value");
  const base64 = value.replaceAll("-", "+").replaceAll("_", "/")
    .padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = globalThis.atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function bytesEqual(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) {
    mismatch |= (left[index] ?? 0) ^ (right[index] ?? 0);
  }
  return mismatch === 0;
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const stableBytes = new Uint8Array(bytes.byteLength);
  stableBytes.set(bytes);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", stableBytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function readLimited(response: Response, maximum: number, label: string): Promise<Uint8Array> {
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maximum) {
    throw new Error(`${label} exceeds ${maximum} bytes`);
  }
  if (!response.body) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > maximum) throw new Error(`${label} exceeds ${maximum} bytes`);
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > maximum) {
        await reader.cancel();
        throw new Error(`${label} exceeds ${maximum} bytes`);
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

function parseJson(bytes: Uint8Array, label: string): unknown {
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch (error) {
    throw new Error(`${label} is not valid UTF-8 JSON`, { cause: error });
  }
}

function trustedOrigins(config: CatalogUpdaterConfig, manifestUrl: URL): Set<string> {
  const configured = config.allowedOrigins?.length
    ? config.allowedOrigins.map((origin) => new URL(origin).origin)
    : [manifestUrl.origin];
  return new Set(configured);
}

function assertRemoteUrl(url: URL, origins: ReadonlySet<string>, label: string): void {
  const localDevelopment =
    (url.hostname === "localhost" || url.hostname === "127.0.0.1") &&
    url.protocol === "http:";
  if (url.protocol !== "https:" && !localDevelopment) {
    throw new Error(`${label} must use HTTPS`);
  }
  if (!origins.has(url.origin)) throw new Error(`${label} origin is not trusted`);
  if (url.username || url.password) throw new Error(`${label} must not contain credentials`);
}

function signaturePayload(manifest: SignedUpdateManifest): Uint8Array {
  const { signature: _signature, ...unsigned } = manifest;
  return new TextEncoder().encode(canonicalJson(unsigned));
}

function satisfiesVersionRange(version: string, range: string): boolean {
  // Deliberately small, fail-closed grammar for release manifests. Complex npm
  // shorthands (`^`, `~`, `||`) are rejected instead of being approximated.
  const clauses = range.trim().split(/(?:\s*,\s*|\s+)/).filter(Boolean);
  if (clauses.length === 0) return false;
  return clauses.every((clause) => {
    const match = clause.match(/^(>=|<=|>|<|=)?v?([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)$/);
    if (!match?.[2]) throw new Error(`Unsupported compatibility range: ${range}`);
    const operator = match[1] ?? "=";
    const comparison = compareCatalogVersions(version, match[2]);
    if (operator === ">=") return comparison >= 0;
    if (operator === "<=") return comparison <= 0;
    if (operator === ">") return comparison > 0;
    if (operator === "<") return comparison < 0;
    if (operator === "=") return comparison === 0;
    return false;
  });
}

export class CatalogUpdater {
  readonly #config: CatalogUpdaterConfig;
  readonly #store: CatalogStore;
  readonly #fetch: typeof globalThis.fetch;

  constructor(config: CatalogUpdaterConfig, store: CatalogStore) {
    this.#config = config;
    this.#store = store;
    this.#fetch = config.fetch ?? globalThis.fetch.bind(globalThis);
  }

  async check(
    currentCatalogVersion: string,
    options: { signal?: AbortSignal } = {}
  ): Promise<CatalogUpdateCheck> {
    if (!this.#config.enabled) return { status: "disabled" };
    const timeoutController = new AbortController();
    const timeout = globalThis.setTimeout(
      () => timeoutController.abort(new DOMException("Update check timed out", "TimeoutError")),
      Math.max(1, this.#config.timeoutMs ?? 15_000)
    );
    const onExternalAbort = () => timeoutController.abort(options.signal?.reason);
    if (options.signal?.aborted) onExternalAbort();
    else options.signal?.addEventListener("abort", onExternalAbort, { once: true });
    const signal = timeoutController.signal;
    try {
      const manifestUrl = new URL(this.#config.manifestUrl, document.baseURI);
      const origins = trustedOrigins(this.#config, manifestUrl);
      assertRemoteUrl(manifestUrl, origins, "Update manifest");
      const manifestResponse = await this.#fetch(manifestUrl.href, {
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        referrerPolicy: "no-referrer",
        headers: { Accept: "application/json" },
        signal
      });
      if (!manifestResponse.ok) {
        throw new Error(`Update manifest: HTTP ${manifestResponse.status}`);
      }
      const manifestBytes = await readLimited(
        manifestResponse,
        this.#config.maxManifestBytes ?? 256 * 1024,
        "Update manifest"
      );
      const manifest = updateManifestSchema.parse(parseJson(manifestBytes, "Update manifest"));
      if (!manifest.signature) throw new Error("Update manifest is unsigned");

      const installed = this.#config.installedVersions;
      if (!installed) throw new Error("Installed ComfyUI/frontend versions are required");
      if (!satisfiesVersionRange(installed.comfyui, manifest.compatibility.comfyui)) {
        throw new Error("Catalog update is incompatible with this ComfyUI version");
      }
      if (!satisfiesVersionRange(installed.frontend, manifest.compatibility.frontend)) {
        throw new Error("Catalog update is incompatible with this frontend version");
      }

      const trustedKeyText = this.#config.publicKeys[manifest.signature.keyId];
      if (!trustedKeyText) throw new Error(`Untrusted signing key: ${manifest.signature.keyId}`);
      const trustedKey = decodeBytes(trustedKeyText);
      const advertisedKey = decodeBytes(manifest.signature.publicKey);
      if (trustedKey.length !== 32 || !bytesEqual(trustedKey, advertisedKey)) {
        throw new Error("Manifest public key does not match the trusted keyring");
      }
      const signature = decodeBytes(manifest.signature.value);
      if (signature.length !== 64) throw new Error("Invalid Ed25519 signature length");
      const valid = await verifyAsync(signature, signaturePayload(manifest), trustedKey);
      if (!valid) throw new Error("Invalid update manifest signature");

      if (compareCatalogVersions(manifest.catalogVersion, currentCatalogVersion) <= 0) {
        return { status: "up-to-date", catalogVersion: manifest.catalogVersion };
      }

      const catalogArtifact = manifest.artifacts.find(
        (artifact) => artifact.contentType.toLowerCase().startsWith("application/json") &&
          artifact.path.endsWith("catalog.json")
      );
      if (!catalogArtifact) throw new Error("Signed manifest has no catalog JSON artifact");
      if (!SAFE_ARTIFACT_PATH.test(catalogArtifact.path) || catalogArtifact.path.includes("..")) {
        throw new Error("Unsafe catalog artifact path");
      }
      const maximum = this.#config.maxCatalogBytes ?? 16 * 1024 * 1024;
      if (catalogArtifact.size > maximum) throw new Error(`Catalog exceeds ${maximum} bytes`);
      const catalogUrl = new URL(catalogArtifact.url);
      assertRemoteUrl(catalogUrl, origins, "Catalog artifact");
      if (!catalogUrl.pathname.endsWith(`/${catalogArtifact.path}`)) {
        throw new Error("Catalog URL does not match its signed path");
      }

      const response = await this.#fetch(catalogUrl.href, {
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        referrerPolicy: "no-referrer",
        headers: { Accept: "application/json" },
        signal
      });
      if (!response.ok) throw new Error(`Catalog artifact: HTTP ${response.status}`);
      const catalogBytes = await readLimited(response, maximum, "Catalog artifact");
      if (catalogBytes.byteLength !== catalogArtifact.size) {
        throw new Error("Catalog artifact size does not match the signed manifest");
      }
      const digest = await sha256Hex(catalogBytes);
      if (digest !== catalogArtifact.sha256) {
        throw new Error("Catalog artifact SHA-256 does not match the signed manifest");
      }
      const rawCatalog = parseJson(catalogBytes, "Catalog artifact");
      assertCompiledCatalog(rawCatalog);
      const catalog = decodeCatalog(rawCatalog, catalogUrl.href);
      if (catalog.catalogVersion !== manifest.catalogVersion) {
        throw new Error("Catalog version does not match the signed manifest");
      }

      return {
        status: "available",
        candidate: Object.freeze({
          catalog,
          manifest,
          keyId: manifest.signature.keyId,
          sha256: digest,
          sourceUrl: catalogUrl.href
        })
      };
    } finally {
      globalThis.clearTimeout(timeout);
      options.signal?.removeEventListener("abort", onExternalAbort);
    }
  }

  async apply(
    candidate: CatalogUpdateCandidate,
    confirm: ConfirmCatalogUpdate
  ): Promise<StoredCatalogRecord | null> {
    if (!(await confirm(candidate))) return null;
    const record: StoredCatalogRecord = {
      catalog: candidate.catalog,
      origin: "signed-update",
      storedAt: new Date().toISOString(),
      sha256: candidate.sha256,
      keyId: candidate.keyId
    };
    await this.#store.commit(record);
    return record;
  }

  /** Atomically swaps active and previous snapshots (last-known-good rollback). */
  rollback(): Promise<StoredCatalogRecord | null> {
    return this.#store.rollback();
  }
}

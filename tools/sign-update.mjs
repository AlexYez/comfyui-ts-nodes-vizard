#!/usr/bin/env node

/** Sign and verify Nodes Wizard update manifests with Ed25519.
 *
 * Trust is never taken from `manifest.signature.publicKey`. Verification needs
 * an independently configured trusted public key supplied through an
 * environment variable. Private seeds are accepted only through an environment
 * variable and are never printed.
 */

import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { readFile, realpath, writeFile } from 'node:fs/promises'
import { basename, isAbsolute, relative, resolve, sep } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import {
  getPublicKeyAsync,
  signAsync,
  verifyAsync
} from '@noble/ed25519'

const CANONICALIZATION = 'comfy-nodes-wizard-json-v1'
const SIGNATURE_SCOPE = 'top-level-manifest-excluding-signature'
const CATALOG_CLI = fileURLToPath(new URL('./catalog.py', import.meta.url))

function fail(message) {
  throw new Error(message)
}

function usage() {
  return `Usage:
  node tools/sign-update.mjs sign --manifest <unsigned.json> --artifact-root <dir> --output <signed.json> [--key-id <id>]
  node tools/sign-update.mjs verify --manifest <signed.json>

Environment:
  NODES_WIZARD_SIGNING_SEED          32-byte private seed, base64url or 64 hex (sign only)
  NODES_WIZARD_TRUSTED_PUBLIC_KEY    trusted 32-byte public key, base64url or 64 hex (verify only)
  NODES_WIZARD_SIGNING_KEY_ID        optional sign key id if --key-id is omitted
  NODES_WIZARD_TRUSTED_KEY_ID        optional expected key id during verification
  NODES_WIZARD_PYTHON                optional Python executable for compiled-catalog validation

The public key embedded in a manifest is informational. Verification succeeds
only against NODES_WIZARD_TRUSTED_PUBLIC_KEY, which must come from trusted app
configuration or deployment secrets.`
}

function parseArgs(argv) {
  if (argv.length === 0 || argv.includes('--help') || argv.includes('-h')) {
    return { help: true }
  }
  const [command, ...rest] = argv
  if (!['sign', 'verify'].includes(command)) fail(`unknown command: ${command}`)
  const options = { command }
  for (let index = 0; index < rest.length; index += 2) {
    const flag = rest[index]
    const value = rest[index + 1]
    if (!flag?.startsWith('--') || value === undefined || value.startsWith('--')) {
      fail(`option ${flag ?? '<missing>'} requires a value`)
    }
    if (!['--manifest', '--artifact-root', '--output', '--key-id'].includes(flag)) {
      fail(`unknown option: ${flag}`)
    }
    options[flag.slice(2).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value
  }
  if (!options.manifest) fail('--manifest is required')
  if (command === 'sign' && !options.output) fail('--output is required for sign')
  if (command === 'sign' && !options.artifactRoot) fail('--artifact-root is required for sign')
  if (command === 'verify' && (options.output || options.keyId || options.artifactRoot)) fail('verify accepts only --manifest')
  return options
}

function decodeKey(value, label) {
  if (!value) fail(`${label} is not configured`)
  let bytes
  if (/^[a-fA-F0-9]{64}$/.test(value)) {
    bytes = Buffer.from(value, 'hex')
  } else if (/^[A-Za-z0-9_-]{43}=?$/.test(value)) {
    bytes = Buffer.from(value.replace(/-/g, '+').replace(/_/g, '/'), 'base64')
  } else {
    fail(`${label} must be 32 bytes encoded as base64url or 64 hex characters`)
  }
  if (bytes.length !== 32) fail(`${label} must decode to exactly 32 bytes`)
  return new Uint8Array(bytes)
}

function decodeSignature(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{86}==$|^[A-Za-z0-9_-]{86}$/.test(value)) {
    fail('manifest signature value is not a 64-byte base64url signature')
  }
  const bytes = Buffer.from(value.replace(/-/g, '+').replace(/_/g, '/'), 'base64')
  if (bytes.length !== 64) fail('manifest signature must decode to exactly 64 bytes')
  return new Uint8Array(bytes)
}

function base64url(bytes) {
  return Buffer.from(bytes).toString('base64url')
}

function canonicalString(value) {
  if (value === null) return 'null'
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) fail('canonical JSON cannot contain non-finite numbers')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${value.map(canonicalString).join(',')}]`
  if (typeof value === 'object') {
    const entries = Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalString(value[key])}`)
    return `{${entries.join(',')}}`
  }
  fail(`canonical JSON cannot contain ${typeof value}`)
}

export function signingBytes(manifest) {
  if (manifest.canonicalization !== CANONICALIZATION) {
    fail(`unsupported canonicalization: ${manifest.canonicalization}`)
  }
  if (manifest.signatureScope !== SIGNATURE_SCOPE) {
    fail(`unsupported signature scope: ${manifest.signatureScope}`)
  }
  const unsigned = structuredClone(manifest)
  delete unsigned.signature
  return new TextEncoder().encode(canonicalString(unsigned))
}

async function readManifest(path) {
  let parsed
  try {
    parsed = JSON.parse(await readFile(path, 'utf8'))
  } catch (error) {
    fail(`cannot read ${path}: ${error.message}`)
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    fail(`${path} must contain one JSON object`)
  }
  return parsed
}

function portableArtifactSegments(value) {
  if (typeof value !== 'string' || value.length === 0 || value.includes('\\') || isAbsolute(value)) {
    fail('catalog artifact path must be a non-empty portable relative path')
  }
  const segments = value.split('/')
  if (segments.some((segment) => segment === '' || segment === '.' || segment === '..' || segment.includes(':'))) {
    fail(`catalog artifact path is unsafe: ${value}`)
  }
  return segments
}

async function localCatalogPreflight(manifest, artifactRoot) {
  if (!Array.isArray(manifest.artifacts)) fail('manifest.artifacts must be an array')
  const catalogArtifacts = manifest.artifacts.filter(
    (artifact) => artifact && typeof artifact === 'object' && typeof artifact.path === 'string' && artifact.path.split('/').at(-1) === 'catalog.json'
  )
  if (catalogArtifacts.length !== 1) {
    fail(`manifest must reference exactly one catalog.json artifact; found ${catalogArtifacts.length}`)
  }
  const artifact = catalogArtifacts[0]
  if (artifact.contentType !== 'application/json') fail('catalog artifact contentType must be application/json')
  if (!Number.isSafeInteger(artifact.size) || artifact.size < 0) fail('catalog artifact size must be a non-negative safe integer')
  if (typeof artifact.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(artifact.sha256)) {
    fail('catalog artifact sha256 must be 64 lowercase hexadecimal characters')
  }

  const rootPath = await realpath(resolve(artifactRoot)).catch((error) => fail(`cannot resolve artifact root ${artifactRoot}: ${error.message}`))
  const candidate = resolve(rootPath, ...portableArtifactSegments(artifact.path))
  const catalogPath = await realpath(candidate).catch((error) => fail(`cannot resolve local catalog artifact ${artifact.path}: ${error.message}`))
  const relativePath = relative(rootPath, catalogPath)
  if (relativePath === '' || relativePath === '..' || relativePath.startsWith(`..${sep}`) || isAbsolute(relativePath)) {
    fail(`catalog artifact leaves --artifact-root: ${artifact.path}`)
  }

  const bytes = await readFile(catalogPath)
  if (bytes.length !== artifact.size) {
    fail(`catalog artifact size mismatch: manifest=${artifact.size}, local=${bytes.length}`)
  }
  const actualHash = createHash('sha256').update(bytes).digest('hex')
  if (actualHash !== artifact.sha256) {
    fail(`catalog artifact SHA-256 mismatch: manifest=${artifact.sha256}, local=${actualHash}`)
  }
  let catalog
  try {
    catalog = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
  } catch (error) {
    fail(`catalog artifact is not strict UTF-8 JSON: ${error.message}`)
  }
  if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog)) {
    fail('catalog artifact must contain one JSON object')
  }
  if (catalog.catalogVersion !== manifest.catalogVersion) {
    fail(`catalogVersion mismatch: manifest=${manifest.catalogVersion}, catalog=${catalog.catalogVersion}`)
  }

  const python = process.env.NODES_WIZARD_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
  const validation = spawnSync(python, [CATALOG_CLI, 'validate-compiled', '-'], {
    encoding: 'utf8',
    input: bytes,
    windowsHide: true,
    maxBuffer: 1024 * 1024
  })
  if (validation.error) fail(`cannot run compiled-catalog validator with ${python}: ${validation.error.message}`)
  if (validation.status !== 0) {
    const detail = (validation.stderr || validation.stdout || '').trim()
    fail(`compiled catalog contract validation failed${detail ? `:\n${detail}` : ''}`)
  }
}

async function signManifest(options) {
  if (options.manifest === options.output) fail('refusing to overwrite the unsigned input; choose a separate --output')
  const manifest = await readManifest(options.manifest)
  await localCatalogPreflight(manifest, options.artifactRoot)
  const seed = decodeKey(process.env.NODES_WIZARD_SIGNING_SEED, 'NODES_WIZARD_SIGNING_SEED')
  const publicKey = await getPublicKeyAsync(seed)
  const keyId = options.keyId || process.env.NODES_WIZARD_SIGNING_KEY_ID
  if (!keyId || !/^[A-Za-z0-9_.:-]{1,100}$/.test(keyId)) {
    fail('a safe key id is required through --key-id or NODES_WIZARD_SIGNING_KEY_ID')
  }
  manifest.signature = null
  const signature = await signAsync(signingBytes(manifest), seed)
  manifest.signature = {
    algorithm: 'Ed25519',
    keyId,
    publicKey: base64url(publicKey),
    value: base64url(signature)
  }
  await writeFile(options.output, `${JSON.stringify(manifest, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' })
  process.stdout.write(`Signed ${basename(options.manifest)} as ${options.output} with key ${keyId}.\n`)
}

async function verifyManifest(options) {
  const manifest = await readManifest(options.manifest)
  const signature = manifest.signature
  if (!signature || typeof signature !== 'object') fail('manifest has no signature')
  if (signature.algorithm !== 'Ed25519') fail(`unsupported signature algorithm: ${signature.algorithm}`)
  const trustedKey = decodeKey(process.env.NODES_WIZARD_TRUSTED_PUBLIC_KEY, 'NODES_WIZARD_TRUSTED_PUBLIC_KEY')
  const trustedKeyId = process.env.NODES_WIZARD_TRUSTED_KEY_ID
  if (trustedKeyId && signature.keyId !== trustedKeyId) {
    fail(`manifest key id ${signature.keyId} does not match trusted key id ${trustedKeyId}`)
  }
  const embeddedKey = decodeKey(signature.publicKey, 'manifest signature.publicKey')
  if (!Buffer.from(embeddedKey).equals(Buffer.from(trustedKey))) {
    fail('manifest public key does not match the independently configured trusted public key')
  }
  const valid = await verifyAsync(decodeSignature(signature.value), signingBytes(manifest), trustedKey)
  if (!valid) fail('invalid Ed25519 signature')
  process.stdout.write(`Verified ${options.manifest} with trusted key ${signature.keyId}.\n`)
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    process.stdout.write(`${usage()}\n`)
    return
  }
  if (options.command === 'sign') await signManifest(options)
  else await verifyManifest(options)
}

main().catch((error) => {
  process.stderr.write(`ERROR: ${error.message}\n`)
  process.exitCode = 1
})

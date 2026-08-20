#!/usr/bin/env node

import { createReadStream, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const fixtureRoot = join(root, "tests", "browser", "site");
const port = Number(process.env.NODES_WIZARD_BROWSER_PORT ?? 4179);

const routes = new Map([
  ["/", join(fixtureRoot, "index.html")],
  ["/scripts/app.js", join(fixtureRoot, "scripts", "app.js")],
  [
    "/extensions/comfyui-ts-nodes-vizard/nodes-wizard.js",
    join(root, "web", "nodes-wizard.js")
  ],
  [
    "/extensions/comfyui-ts-nodes-vizard/data/catalog.json",
    join(root, "web", "data", "catalog.json")
  ],
  [
    "/object_info",
    join(root, "content", "runtime", "comfyui-0.32.0.object-info.sample.json")
  ]
]);

const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8"
};

createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  if (url.pathname === "/system_stats") {
    const payload = JSON.stringify({
      system: {
        comfyui_version: "0.32.0",
        comfy_package_versions: [
          {
            name: "comfyui-frontend-package",
            installed: "1.48.7",
            required: "1.48.7"
          }
        ]
      },
      devices: []
    });
    response.writeHead(200, {
      "Cache-Control": "no-store",
      "Content-Length": Buffer.byteLength(payload),
      "Content-Type": "application/json; charset=utf-8"
    });
    response.end(payload);
    return;
  }
  if (url.pathname === "/object_info") {
    const sourceText = readFileSync(
      join(root, "content", "runtime", "comfyui-0.32.0.object-info.sample.json"),
      "utf8"
    ).trimEnd();
    const futureNode = {
      input: { required: { value: ["INT", { default: 1, min: 0 }] } },
      output: ["INT"],
      output_name: ["INT"],
      python_module: "nodes",
      category: "utils",
      display_name: "Future Core Node",
      description: "A node added after the bundled catalog was published."
    };
    // Preserve Python-emitted number lexemes (8.0, uint64 maxima) in the fixture.
    const payload = `${sourceText.slice(0, -1)},"FutureCoreNode":${JSON.stringify(futureNode)}}`;
    response.writeHead(200, {
      "Cache-Control": "no-store",
      "Content-Length": Buffer.byteLength(payload),
      "Content-Type": "application/json; charset=utf-8"
    });
    response.end(payload);
    return;
  }
  const file = routes.get(url.pathname);
  if (!file) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  const resolved = resolve(normalize(file));
  if (!resolved.startsWith(root) || !statSync(resolved).isFile()) {
    response.writeHead(403);
    response.end();
    return;
  }

  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Length": statSync(resolved).size,
    "Content-Type": contentTypes[extname(resolved)] ?? "application/octet-stream"
  });
  createReadStream(resolved).pipe(response);
}).listen(port, "127.0.0.1", () => {
  process.stdout.write(`TS Nodes Wizard browser harness: http://127.0.0.1:${port}\n`);
});

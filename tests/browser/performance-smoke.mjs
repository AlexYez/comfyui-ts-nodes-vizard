// Real-browser qualification of the packaged extension against a minimal Comfy API.
// WIZARD_PLAYWRIGHT_MODULE may point to an existing Playwright installation.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../../", import.meta.url));
const webRoot = path.resolve(process.env.WIZARD_WEB_ROOT || path.join(root, "web"));
const { chromium } = await import(process.env.WIZARD_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.WIZARD_PLAYWRIGHT_MODULE).href : "playwright");
const prefix = "/extensions/renamed-wizard";
const requests = [];
const runtime = await readFile(process.env.WIZARD_RUNTIME_INVENTORY || path.join(root, "content/runtime/comfyui-0.32.0.object-info.json"));
const runtimeNodes = JSON.parse(runtime);
const septemberEvidence = JSON.parse(await readFile(path.join(root, "content/research/september-2026-articles.json"), "utf8"));
const septemberNodes = Object.keys(septemberEvidence.articles).filter(id => runtimeNodes[id]);
const octoberEvidence = JSON.parse(await readFile(path.join(root, "content/research/october-2026-update.json"), "utf8"));
const articleNodes = [...new Set([...septemberNodes, ...Object.keys(octoberEvidence.officialWorkflowOccurrences).filter(id => runtimeNodes[id])])];
const systemStats = process.env.WIZARD_SYSTEM_STATS ? await readFile(process.env.WIZARD_SYSTEM_STATS)
  : JSON.stringify({system:{comfyui_version:"0.32.0",comfy_package_versions:[{name:"comfyui-frontend-package",installed:"1.48.7"}]}});
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost").pathname;
  requests.push(url);
  try {
    let body;
    let mime = "text/javascript";
    if (url === "/") {
      mime = "text/html";
      body = `<html lang="ru"><button id="open">Open Wizard</button><button id="node">KSampler docs</button><button id="note">Note docs</button><input id="node-id"><button id="new-node">Node docs</button>
        <script>window.longTasks=[];new PerformanceObserver(list=>window.longTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true});</script>
        <script type="module" src="${prefix}/nodes-wizard.js"></script></html>`;
    } else if (url === "/scripts/app.js") {
      body = `export const app={extensionManager:{setting:{get:()=>"ru"}},api:{fetchApi:(url,options)=>fetch(url,options)},registerExtension(extension){
        extension.setup?.();
        document.querySelector('#open').onclick=()=>extension.commands[0].function();
        document.querySelector('#node').onclick=()=>extension.getNodeMenuItems({comfyClass:'KSampler'}).filter(Boolean)[0].callback();
        document.querySelector('#note').onclick=()=>extension.getNodeMenuItems({type:'Note'}).filter(Boolean)[0].callback();
        document.querySelector('#new-node').onclick=()=>extension.getNodeMenuItems({comfyClass:document.querySelector('#node-id').value}).filter(Boolean)[0].callback();
        document.body.dataset.ready='true';
      }};`;
    } else if (url === "/object_info") { body = runtime; mime = "application/json"; }
    else if (url === "/system_stats") { body = systemStats; mime = "application/json"; }
    else if (url.startsWith(`${prefix}/`)) {
      const relative = url.slice(prefix.length + 1);
      const target = path.resolve(webRoot, relative);
      if (!target.startsWith(webRoot + path.sep)) throw new Error("Invalid path");
      body = await readFile(target);
      if (target.endsWith(".json")) mime = "application/json";
    } else { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": mime, "Cache-Control": "no-store" });
    res.end(body);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true, ...(process.env.WIZARD_BROWSER_CHANNEL ? { channel: process.env.WIZARD_BROWSER_CHANNEL } : {}) });
  const page = await browser.newPage();
  const errors = [];
  const workers = new Set();
  page.on("pageerror", error => errors.push(String(error)));
  page.on("worker", worker => { workers.add(worker); worker.on("close", () => workers.delete(worker)); });
  const waitForWorkersToStop = async () => {
    const deadline = Date.now() + 5_000;
    while (workers.size && Date.now() < deadline) await page.waitForTimeout(50);
    assert.equal(workers.size, 0);
  };
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForSelector('body[data-ready="true"]');
  await page.waitForTimeout(300);
  assert.equal(requests.some(url => url.includes("catalog.json") || url === "/object_info"), false);
  assert.equal(requests.some(url => /chunks|workers/.test(url)), false);
  assert.equal(workers.size, 0);
  const initialRequests = [...requests];

  await page.locator("#node").click();
  await page.locator(".nw-title").waitFor();
  assert.equal(await page.locator(".nw-kicker").first().textContent(), "KSampler");
  await page.locator(".nw-markdown h2").first().waitFor();
  assert.ok((await page.locator(".nw-runtime").textContent()).includes("18446744073709551615"));
  const scroll = page.locator(".nw-main");
  await scroll.evaluate(el => { el.scrollTop = 300; el.dispatchEvent(new Event('scroll')); });
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  assert.equal(await page.locator(".nw-shell").count(), 0);
  await page.locator("#open").click();
  await page.waitForFunction(() => document.querySelector('#comfyui-ts-nodes-vizard-host').shadowRoot.querySelector('.nw-main')?.scrollTop >= 290);
  await page.getByRole("button", { name: "Каталог", exact: true }).click();
  assert.equal(await page.locator(".nw-result").count(), 40);
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  assert.equal(await page.locator(".nw-result").count(), 40);
  await page.getByRole("searchbox").fill("KSampler");
  await page.waitForTimeout(250);
  await page.getByText("Поиск…", { exact: true }).waitFor({ state: "hidden" });
  assert.ok((await page.locator(".nw-result").allTextContents()).some(text => text.includes("KSampler")));
  assert.ok(workers.size >= 1);
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await waitForWorkersToStop();
  assert.equal(await page.locator(".nw-shell").count(), 0);
  await page.locator("#open").click();
  await page.getByRole("searchbox").fill("ControlNet");
  await page.waitForTimeout(250);
  await page.getByText("Поиск…", { exact: true }).waitFor({ state: "hidden" });
  assert.ok(await page.locator(".nw-result").count() > 0);
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await waitForWorkersToStop();
  assert.deepEqual(errors, []);
  const frontendPage = await browser.newPage();
  frontendPage.on("pageerror", error => errors.push(String(error)));
  await frontendPage.goto(`http://127.0.0.1:${server.address().port}`);
  await frontendPage.waitForSelector('body[data-ready="true"]');
  await frontendPage.locator("#note").click();
  await frontendPage.locator(".nw-title").waitFor();
  assert.equal(await frontendPage.locator(".nw-kicker").first().textContent(), "Note");
  await frontendPage.close();
  for (const nodeId of articleNodes) {
    await page.locator('#node-id').fill(nodeId);
    await page.locator('#new-node').click();
    await page.waitForFunction(id => document.querySelector('#comfyui-ts-nodes-vizard-host').shadowRoot.querySelector('.nw-kicker')?.textContent === id, nodeId);
    const markdown = page.locator('.nw-markdown');
    assert.match(await markdown.textContent(), /пример/iu, nodeId);
    assert.match(await markdown.textContent(), /ограничения/iu, nodeId);
    await page.getByRole('button', { name: 'Закрыть', exact: true }).click();
    await waitForWorkersToStop();
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ initialRequests, catalogRequests: requests.filter(url => url.endsWith("catalog.json")).length,
    articlesOpened: articleNodes.length, finalWorkers: workers.size, longTasksMs: await page.evaluate(() => window.longTasks), errors }, null, 2));
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}

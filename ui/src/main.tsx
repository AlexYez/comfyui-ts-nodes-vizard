import { app as comfyApp } from "/scripts/app.js";

import type { WizardController } from "./app/controller";
import { ComfyBridge } from "./bridge/ComfyBridge";
import type { ComfyAppLike } from "./types/comfy";
import { exactNodeClassType } from "./runtime/identity";

const bridge = new ComfyBridge(comfyApp as ComfyAppLike);
let controller: WizardController | undefined;
let loading: Promise<WizardController> | undefined;
let pending: { classType?: string } | undefined;

function open(request?: { classType?: string }): void {
  pending = request;
  if (controller) { controller.open(request); return; }
  if (loading) return;
  loading = import("./app/start").then(({ startWizard }) => {
    controller = startWizard(bridge, new URL(/* @vite-ignore */ "./data/catalog.json", import.meta.url).href);
    controller.open(pending);
    return controller;
  }).catch((error: unknown) => {
    bridge.toast("error", "TS Nodes Wizard", String(error));
    throw error;
  });
  void loading.catch(() => { loading = undefined; });
}

bridge.register({
  setup: () => {},
  open,
  resolveClassType: (node) => controller?.resolveClassType(node) ?? exactNodeClassType(node) ??
    (typeof node.type === "string" && ["Reroute", "Note", "MarkdownNote", "PrimitiveNode"].includes(node.type) ? node.type : null),
  locale: () => controller?.getSnapshot().locale ??
    bridge.app.extensionManager?.setting?.get<string>("Comfy.Locale") ?? document.documentElement.lang ?? "ru"
});

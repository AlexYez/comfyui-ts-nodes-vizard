import { app as comfyApp } from "/scripts/app.js";

import { WizardController } from "./app/controller";
import { ComfyBridge } from "./bridge/ComfyBridge";
import type { ComfyAppLike } from "./types/comfy";
import { mountWizard } from "./ui/mount";

const bridge = new ComfyBridge(comfyApp as ComfyAppLike);
const controller = new WizardController({ bridge });
let mounted = false;

bridge.register({
  setup: () => {
    if (!mounted) {
      mountWizard(controller);
      mounted = true;
    }
    void controller.initialise();
  },
  open: (request) => controller.open(request),
  resolveClassType: (node) => controller.resolveClassType(node),
  locale: () => controller.getSnapshot().locale
});

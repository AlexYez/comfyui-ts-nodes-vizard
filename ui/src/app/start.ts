import { WizardController } from "./controller";
import type { ComfyBridge } from "../bridge/ComfyBridge";
import { mountWizard } from "../ui/mount";

export function startWizard(bridge: ComfyBridge, catalogUrl: string): WizardController {
  const controller = new WizardController({ bridge, catalogUrls: [catalogUrl] });
  mountWizard(controller);
  return controller;
}

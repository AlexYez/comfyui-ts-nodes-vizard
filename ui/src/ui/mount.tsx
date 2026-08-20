import { createRoot, type Root } from "react-dom/client";

import type { WizardController } from "../app/controller";
import { Drawer } from "./Drawer";
import { wizardStyles } from "./styles";

const HOST_ID = "comfyui-ts-nodes-vizard-host";

export interface WizardMount {
  host: HTMLElement;
  destroy: () => void;
}

export function mountWizard(controller: WizardController): WizardMount {
  const existing = document.getElementById(HOST_ID);
  existing?.remove();

  const host = document.createElement("div");
  host.id = HOST_ID;
  const shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = wizardStyles;
  const container = document.createElement("div");
  shadow.append(style, container);
  document.body.appendChild(host);

  const root: Root = createRoot(container);
  root.render(<Drawer controller={controller} />);

  return {
    host,
    destroy: () => {
      root.unmount();
      host.remove();
    }
  };
}

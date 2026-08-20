import type {
  ComfyAppLike,
  ComfyExtensionLike,
  ComfyNodeLike
} from "../types/comfy";
import { decodeObjectInfo, parseObjectInfoText } from "../runtime/objectInfo";
import { decodeSystemVersions, type ComfySystemVersions } from "../runtime/systemVersions";
import type { RuntimeNodeDefinition } from "../types/contracts";

export const OPEN_COMMAND_ID = "nodes-wizard.open";

export interface WizardExtensionCallbacks {
  setup: () => void | Promise<void>;
  open: (request?: { classType?: string }) => void;
  resolveClassType: (node: ComfyNodeLike) => string | null;
  locale: () => string;
}

export class ComfyBridge {
  readonly app: ComfyAppLike;

  constructor(app: ComfyAppLike) {
    this.app = app;
  }

  register(callbacks: WizardExtensionCallbacks): void {
    const extension: ComfyExtensionLike = {
      name: "comfyui-ts-nodes-vizard.frontend",
      setup: callbacks.setup,
      commands: [
        {
          id: OPEN_COMMAND_ID,
          label: "Open TS Nodes Wizard",
          icon: "pi pi-book",
          function: () => callbacks.open()
        }
      ],
      menuCommands: [
        {
          path: ["Extensions", "TS Nodes Wizard"],
          commands: [OPEN_COMMAND_ID]
        }
      ],
      actionBarButtons: [
        {
          icon: "pi pi-book",
          label: "TS Nodes Wizard",
          tooltip: "Open the node reference",
          class: "nodes-wizard-action",
          onClick: () => callbacks.open()
        }
      ],
      getNodeMenuItems: (node) => {
        const classType = callbacks.resolveClassType(node);
        if (!classType) return [];
        const ru = callbacks.locale().toLowerCase().startsWith("ru");
        return [
          null,
          {
            content: ru ? "Открыть в TS Nodes Wizard" : "Open in TS Nodes Wizard",
            callback: () => callbacks.open({ classType })
          }
        ];
      }
    };
    this.app.registerExtension(extension);
  }

  async fetchObjectInfo(signal?: AbortSignal): Promise<Map<string, RuntimeNodeDefinition>> {
    const response = this.app.api?.fetchApi
      ? await this.app.api.fetchApi("/object_info", { signal })
      : await fetch("/object_info", {
          signal,
          headers: { Accept: "application/json" },
          credentials: "same-origin"
        });
    if (!response.ok) throw new Error(`/object_info: HTTP ${response.status}`);
    return decodeObjectInfo(parseObjectInfoText(await response.text()));
  }

  async fetchSystemVersions(signal?: AbortSignal): Promise<ComfySystemVersions> {
    const response = this.app.api?.fetchApi
      ? await this.app.api.fetchApi("/system_stats", { signal })
      : await fetch("/system_stats", {
          signal,
          headers: { Accept: "application/json" },
          credentials: "same-origin"
        });
    if (!response.ok) throw new Error(`/system_stats: HTTP ${response.status}`);
    return decodeSystemVersions(await response.json());
  }

  renderMarkdown(markdown: string, baseUrl?: string): string | undefined {
    return this.app.extensionManager?.renderMarkdownToHtml?.(markdown, baseUrl);
  }

  toast(
    severity: "success" | "info" | "warn" | "error",
    summary: string,
    detail?: string
  ): void {
    this.app.extensionManager?.toast?.add({ severity, summary, detail, life: 4500 });
  }

  async confirm(title: string, message: string): Promise<boolean> {
    const native = this.app.extensionManager?.dialog?.confirm;
    if (native) return (await native({ title, message, type: "default" })) === true;
    return globalThis.confirm(`${title}\n\n${message}`);
  }

  /** Opens a separate temporary workflow tab. It never mutates the active graph. */
  async openTemporaryWorkflow(workflowData: Record<string, unknown>): Promise<boolean> {
    const workflowStore = this.app.extensionManager?.workflow;
    if (!workflowStore) return false;
    try {
      const workflow = await workflowStore.createNewTemporary(undefined, workflowData);
      await workflowStore.openWorkflow(workflow);
      return true;
    } catch {
      return false;
    }
  }
}

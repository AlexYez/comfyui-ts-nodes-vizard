export interface ComfyNodeLike {
  comfyClass?: unknown;
  type?: unknown;
  title?: unknown;
}

export interface ComfyContextMenuItem {
  content?: string;
  title?: string;
  className?: string;
  disabled?: boolean;
  callback?: () => void | boolean | Promise<void | boolean>;
  submenu?: { options: Array<ComfyContextMenuItem | null> };
}

export interface ComfyCommandLike {
  id: string;
  label: string;
  icon?: string;
  function: () => void | Promise<void>;
  active?: () => boolean;
}

export interface ComfyExtensionLike {
  name: string;
  setup?: () => void | Promise<void>;
  getNodeMenuItems?: (
    node: ComfyNodeLike
  ) => Array<ComfyContextMenuItem | null>;
  commands?: ComfyCommandLike[];
  menuCommands?: Array<{ path: string[]; commands: string[] }>;
  actionBarButtons?: Array<{
    icon: string;
    label?: string;
    tooltip?: string;
    class?: string;
    onClick: () => void;
  }>;
}

export interface ComfyExtensionManagerLike {
  renderMarkdownToHtml?: (markdown: string, baseUrl?: string) => string;
  toast?: {
    add: (message: {
      severity?: "success" | "info" | "warn" | "error";
      summary?: string;
      detail?: string;
      life?: number;
    }) => void;
  };
  dialog?: {
    confirm?: (options: {
      title: string;
      message: string;
      type?: "default" | "overwrite" | "delete" | "dirtyClose" | "reinstall";
      itemList?: string[];
      hint?: string;
    }) => Promise<boolean | null>;
  };
  setting?: {
    get: <T = unknown>(id: string) => T | undefined;
  };
  workflow?: {
    createNewTemporary: (
      path?: string,
      workflowData?: Record<string, unknown>
    ) => unknown | Promise<unknown>;
    openWorkflow: (workflow: unknown) => void | Promise<void>;
  };
}

export interface ComfyApiLike {
  fetchApi?: (route: string, options?: RequestInit) => Promise<Response>;
}

export interface ComfyAppLike {
  registerExtension: (extension: ComfyExtensionLike) => void;
  extensionManager?: ComfyExtensionManagerLike;
  api?: ComfyApiLike;
}

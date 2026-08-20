const extensionManager = {
  setting: { get: (id) => (id === "Comfy.Locale" ? "ru" : undefined) },
  toast: { add: (message) => console.info("toast", message) },
  dialog: { confirm: async () => true },
  workflow: {
    createNewTemporary: async (_path, workflowData) => ({ workflowData }),
    openWorkflow: async (workflow) => console.info("temporary workflow", workflow)
  }
};

export const app = {
  api: { fetchApi: (route, options) => fetch(route, options) },
  extensionManager,
  registerExtension(extension) {
    this.extension = extension;
  }
};

globalThis.__COMFY_APP__ = app;


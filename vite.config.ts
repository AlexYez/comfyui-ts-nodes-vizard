import { cp, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

function copyCatalog(): Plugin {
  return {
    name: "nodes-wizard-copy-catalog",
    async closeBundle() {
      const source = path.join(rootDir, "content", "generated");
      const target = path.join(rootDir, "web", "data");
      await mkdir(target, { recursive: true });
      await cp(source, target, { recursive: true, force: true });
    }
  };
}

function rewriteComfyImports(mode: string): Plugin {
  return {
    name: "nodes-wizard-comfy-imports",
    resolveId(source) {
      if (mode !== "development") return null;
      if (source === "/scripts/app.js" || source === "/scripts/api.js") {
        return `http://127.0.0.1:8188${source}`;
      }
      return null;
    }
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), rewriteComfyImports(mode), copyCatalog()],
  build: {
    emptyOutDir: false,
    outDir: path.join(rootDir, "web"),
    // The packaged extension ships prebuilt code; source maps add over a
    // megabyte to every Manager install and are not needed at runtime.
    sourcemap: false,
    target: "es2022",
    rollupOptions: {
      external: ["/scripts/app.js", "/scripts/api.js"],
      input: path.join(rootDir, "ui", "src", "main.tsx"),
      output: {
        entryFileNames: "nodes-wizard.js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
        inlineDynamicImports: true
      }
    }
  },
  server: {
    cors: true,
    host: "127.0.0.1",
    port: 5173
  }
}));

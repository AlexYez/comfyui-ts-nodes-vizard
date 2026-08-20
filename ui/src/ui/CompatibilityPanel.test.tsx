import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WizardController, WizardSnapshot } from "../app/controller";
import { CompatibilityPanel } from "./CompatibilityPanel";

describe("CompatibilityPanel update presentation", () => {
  it("shows signed size, bounded concrete changes, rollback, and the persistent toggle", () => {
    const setUpdatesEnabled = vi.fn();
    const snapshot: WizardSnapshot = {
      open: true,
      phase: "ready",
      locale: "ru",
      query: "",
      warnings: [],
      canGoBack: false,
      canGoForward: false,
      panel: "compatibility",
      versions: { backend: "0.32.0", frontend: "1.48.7" },
      updatesEnabled: true,
      updateConfigured: true,
      canRollback: true,
      update: {
        status: "available",
        version: "2.0.0",
        summary: "Безопасное обновление каталога.",
        artifactSize: 2048,
        checkedAt: "2026-08-13T00:00:00Z",
        changes: {
          added: { total: 14, items: ["core.one", "core.two"] },
          updated: { total: 1, items: ["core.updated"] },
          deprecated: { total: 0, items: [] },
          removed: { total: 1, items: ["core.removed"] }
        }
      }
    };
    const controller = {
      getSnapshot: () => snapshot,
      setUpdatesEnabled,
      checkForUpdates: vi.fn(),
      installAvailableUpdate: vi.fn(),
      rollbackCatalog: vi.fn()
    } as unknown as WizardController;
    render(<CompatibilityPanel controller={controller} />);
    expect(screen.getByText(/2 KiB/)).toBeInTheDocument();
    expect(screen.getByText("core.one")).toBeInTheDocument();
    expect(screen.getByText("+12 ещё")).toBeInTheDocument();
    expect(screen.getByText("Откатить к предыдущему каталогу")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(setUpdatesEnabled).toHaveBeenCalledWith(false);
  });
});

import { describe, expect, it } from "vitest";

import {
  DailyUpdateSchedule,
  UpdatePreference,
  updateConfigurationReady
} from "./updateSchedule";

describe("daily update scheduling", () => {
  it("is fail-closed when the URL, keyring, or installed versions are missing", () => {
    expect(updateConfigurationReady({ enabled: true, manifestUrl: "", publicKeys: {} }))
      .toBe(false);
    expect(updateConfigurationReady({
      enabled: true,
      manifestUrl: "https://updates.example/manifest.json",
      publicKeys: { release: "key" }
    })).toBe(false);
  });

  it("checks at most once per 24-hour window", () => {
    const values = new Map<string, string>();
    const schedule = new DailyUpdateSchedule({
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => { values.set(key, value); }
    });
    expect(schedule.isDue(1_000_000)).toBe(true);
    schedule.markChecked(1_000_000);
    expect(schedule.isDue(1_000_000 + 23 * 60 * 60 * 1000)).toBe(false);
    expect(schedule.isDue(1_000_000 + 24 * 60 * 60 * 1000)).toBe(true);
  });

  it("persists an explicit user network-check preference and defaults enabled", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); }
    };
    const preference = new UpdatePreference(storage);
    expect(preference.isEnabled()).toBe(true);
    preference.setEnabled(false);
    expect(new UpdatePreference(storage).isEnabled()).toBe(false);
    preference.setEnabled(true);
    expect(preference.isEnabled()).toBe(true);
  });
});

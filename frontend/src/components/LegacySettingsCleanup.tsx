"use client";
import { useEffect } from "react";
import { clearLegacySettings } from "@/lib/legacy-settings";

export function LegacySettingsCleanup() {
  useEffect(() => {
    try {
      clearLegacySettings(window.localStorage);
    } catch {
      /* Storage may be blocked. The new app never reads saved credentials. */
    }
  }, []);
  return null;
}

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  emptySettings,
  normalizeSettings,
  readSettings,
  SETTINGS_KEY,
  writeSettings,
  type SavedSettings,
} from "@/lib/settings-storage";

interface SaveResult {
  ok: boolean;
  message?: string;
}
interface ApiKeyState {
  apiKey: string;
  llmEnabled: boolean;
  hydrated: boolean;
  storageAvailable: boolean;
  storageMessage: string | null;
  saveSettings: (key: string, enabled: boolean) => SaveResult;
  setLlmEnabled: (enabled: boolean) => SaveResult;
  clearApiKey: () => SaveResult;
}
const ApiKeyContext = createContext<ApiKeyState | null>(null);

export function ApiKeyProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<SavedSettings>(emptySettings);
  const [hydrated, setHydrated] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const [storageMessage, setStorageMessage] = useState<string | null>(null);
  useEffect(() => {
    const load = () => {
      try {
        setSettings(readSettings(window.localStorage));
        setStorageAvailable(true);
        setStorageMessage(null);
      } catch {
        setStorageAvailable(false);
        setStorageMessage(
          "Browser storage is unavailable. Changes will last only in this open page.",
        );
      }
      setHydrated(true);
    };
    load();
    const sync = (event: StorageEvent) => {
      if (event.key === SETTINGS_KEY || event.key === null) load();
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  const saveSettings = useCallback(
    (key: string, enabled: boolean): SaveResult => {
      let next: SavedSettings;
      try {
        next = normalizeSettings(key, enabled);
      } catch (error) {
        return {
          ok: false,
          message:
            error instanceof Error ? error.message : "Check your settings.",
        };
      }
      try {
        writeSettings(window.localStorage, next);
        setStorageAvailable(true);
        setStorageMessage(null);
      } catch {
        setStorageAvailable(false);
        setStorageMessage(
          next.apiKey
            ? "Settings are active for this page, but could not be saved in this browser."
            : "The key was cleared from this page, but saved browser data could not be removed. Clear this site's data in your browser.",
        );
      }
      setSettings(next);
      return { ok: true };
    },
    [],
  );
  const value = useMemo<ApiKeyState>(
    () => ({
      apiKey: settings.apiKey,
      llmEnabled: settings.llmEnabled,
      hydrated,
      storageAvailable,
      storageMessage,
      saveSettings,
      setLlmEnabled: (enabled) => saveSettings(settings.apiKey, enabled),
      clearApiKey: () => saveSettings("", false),
    }),
    [settings, hydrated, storageAvailable, storageMessage, saveSettings],
  );
  return (
    <ApiKeyContext.Provider value={value}>{children}</ApiKeyContext.Provider>
  );
}
export function useApiKey(): ApiKeyState {
  const context = useContext(ApiKeyContext);
  if (!context)
    throw new Error("useApiKey must be used within ApiKeyProvider.");
  return context;
}

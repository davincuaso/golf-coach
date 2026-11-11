export const SETTINGS_KEY = "golf-coach:byok:v1";
export interface SavedSettings {
  version: 1;
  apiKey: string;
  llmEnabled: boolean;
}
export const emptySettings: SavedSettings = {
  version: 1,
  apiKey: "",
  llmEnabled: false,
};
export interface SettingsStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function normalizeSettings(
  apiKey: string,
  llmEnabled: boolean,
): SavedSettings {
  const key = apiKey.trim();
  if (key.length > 1024 || /[^\x21-\x7E]|,/.test(key))
    throw new Error("Enter a key without spaces or unsupported characters.");
  if (llmEnabled && !key)
    throw new Error("Add an API key before enabling AI coaching.");
  return { version: 1, apiKey: key, llmEnabled };
}
export function readSettings(storage: SettingsStorage): SavedSettings {
  const raw = storage.getItem(SETTINGS_KEY);
  if (!raw) return { ...emptySettings };
  try {
    const value: unknown = JSON.parse(raw);
    if (
      !value ||
      typeof value !== "object" ||
      !("version" in value) ||
      value.version !== 1 ||
      !("apiKey" in value) ||
      typeof value.apiKey !== "string" ||
      !("llmEnabled" in value) ||
      typeof value.llmEnabled !== "boolean"
    )
      return { ...emptySettings };
    return normalizeSettings(value.apiKey, value.llmEnabled);
  } catch {
    return { ...emptySettings };
  }
}
export function writeSettings(
  storage: SettingsStorage,
  value: SavedSettings,
): void {
  const normalized = normalizeSettings(value.apiKey, value.llmEnabled);
  if (!normalized.apiKey && !normalized.llmEnabled)
    storage.removeItem(SETTINGS_KEY);
  else storage.setItem(SETTINGS_KEY, JSON.stringify(normalized));
}

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  emptySettings,
  normalizeSettings,
  readSettings,
  SETTINGS_KEY,
  writeSettings,
  type SettingsStorage,
} from "../src/lib/settings-storage.ts";
function store(): SettingsStorage & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => {
      data.set(key, value);
    },
    removeItem: (key) => {
      data.delete(key);
    },
  };
}
test("BYOK settings survive reload, including an off toggle with a remembered key", () => {
  const storage = store();
  assert.deepEqual(readSettings(storage), emptySettings);
  writeSettings(storage, normalizeSettings("  sk-test-only  ", true));
  assert.deepEqual(readSettings(storage), {
    version: 1,
    apiKey: "sk-test-only",
    llmEnabled: true,
  });
  writeSettings(storage, normalizeSettings("sk-test-only", false));
  assert.equal(readSettings(storage).llmEnabled, false);
  assert.equal(readSettings(storage).apiKey, "sk-test-only");
});
test("forget removes only Golf Coach settings", () => {
  const storage = store();
  storage.data.set("unrelated", "preserve");
  writeSettings(storage, normalizeSettings("sk-test-only", true));
  writeSettings(storage, emptySettings);
  assert.equal(storage.getItem(SETTINGS_KEY), null);
  assert.equal(storage.getItem("unrelated"), "preserve");
});
test("corrupted, unsupported, or unsafe saved data disables synthesis", () => {
  const storage = store();
  for (const value of [
    "{",
    "null",
    '{"version":2,"apiKey":"sk-test","llmEnabled":true}',
    '{"version":1,"apiKey":"","llmEnabled":true}',
    '{"version":1,"apiKey":"bad key","llmEnabled":true}',
  ]) {
    storage.data.set(SETTINGS_KEY, value);
    assert.deepEqual(readSettings(storage), emptySettings);
  }
  for (const value of [
    "bad\r\nHeader",
    "has spaces",
    "two,keys",
    "x".repeat(1025),
  ])
    assert.throws(() => normalizeSettings(value, true));
  assert.throws(() => normalizeSettings("", true));
});
test("storage denial propagates so the context can report memory-only mode", () => {
  const storage: SettingsStorage = {
    getItem() {
      throw new DOMException("Denied", "SecurityError");
    },
    setItem() {
      throw new Error("Quota");
    },
    removeItem() {
      throw new Error("Denied");
    },
  };
  assert.throws(() => readSettings(storage));
  assert.throws(() =>
    writeSettings(storage, normalizeSettings("sk-test-only", false)),
  );
});

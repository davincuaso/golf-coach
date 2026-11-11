import { test } from "node:test";
import assert from "node:assert/strict";
import { copyCoachingPrompt } from "../src/lib/clipboard.ts";
import { clearLegacySettings } from "../src/lib/legacy-settings.ts";

test("copy preserves the exact multi-line coaching prompt", async () => {
  const values: string[] = [];
  const prompt =
    'Act as a master golf professional.\n{"tempo_ratio":3,"missing":null}\n';
  await copyCoachingPrompt(prompt, {
    writeText: async (text) => {
      values.push(text);
    },
  });
  assert.deepEqual(values, [prompt]);
});
test("copy failures remain failures so the UI offers manual selection", async () => {
  await assert.rejects(
    copyCoachingPrompt("prompt", undefined),
    /Clipboard unavailable/,
  );
  await assert.rejects(
    copyCoachingPrompt("prompt", {
      writeText: async () => {
        throw new DOMException("Denied", "NotAllowedError");
      },
    }),
    { name: "NotAllowedError" },
  );
});
test("migration deletes only retired settings and never reads credentials", () => {
  const data = new Map([
    ["golf-coach:byok:v1", "retired secret"],
    ["another-app", "preserve"],
  ]);
  clearLegacySettings({
    removeItem: (key) => {
      data.delete(key);
    },
  });
  assert.equal(data.has("golf-coach:byok:v1"), false);
  assert.equal(data.get("another-app"), "preserve");
});

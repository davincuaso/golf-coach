/** Keep clipboard access behind an explicit user gesture, with visible failure. */
export async function copyCoachingPrompt(
  prompt: string,
  clipboard: Pick<Clipboard, "writeText"> | undefined,
): Promise<void> {
  if (!clipboard)
    throw new Error(
      "Clipboard unavailable. Select the prompt and copy it manually.",
    );
  await clipboard.writeText(prompt);
}

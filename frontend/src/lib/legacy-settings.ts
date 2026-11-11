/** Delete only the retired app's saved key. Never read or migrate credentials. */
export function clearLegacySettings(
  storage: Pick<Storage, "removeItem">,
): void {
  storage.removeItem("golf-coach:byok:v1");
}

/** Shared API authentication. Called inside the route as well as middleware. */
export interface AccessEnvironment {
  NODE_ENV?: string;
  GOLF_WEB_USERNAME?: string;
  GOLF_WEB_PASSWORD?: string;
}
export function isLoopback(hostname: string): boolean {
  return ["localhost", "127.0.0.1", "[::1]", "::1"].includes(
    hostname.toLowerCase(),
  );
}
export async function workspaceAccess(
  request: Request,
  env: AccessEnvironment,
): Promise<"allowed" | "unauthorized" | "unconfigured"> {
  if (
    env.NODE_ENV === "development" &&
    isLoopback(new URL(request.url).hostname)
  )
    return "allowed";
  if (!env.GOLF_WEB_PASSWORD || env.GOLF_WEB_PASSWORD.length < 16)
    return "unconfigured";
  const value = request.headers.get("authorization") ?? "";
  if (!value.toLowerCase().startsWith("basic ")) return "unauthorized";
  try {
    const decoded = atob(value.slice(6));
    const expected = `${env.GOLF_WEB_USERNAME || "coach"}:${env.GOLF_WEB_PASSWORD}`;
    const digest = async (text: string) =>
      new Uint8Array(
        await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)),
      );
    const [a, b] = await Promise.all([digest(decoded), digest(expected)]);
    let difference = 0;
    for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
    return difference === 0 ? "allowed" : "unauthorized";
  } catch {
    return "unauthorized";
  }
}

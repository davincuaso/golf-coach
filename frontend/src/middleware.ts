import { NextRequest, NextResponse } from "next/server";
import { workspaceAccess } from "@/lib/workspace-auth";

export async function middleware(request: NextRequest) {
  const access = await workspaceAccess(request, process.env);
  if (access !== "allowed")
    return new NextResponse(
      access === "unconfigured"
        ? "Workspace access is not configured. Set GOLF_WEB_PASSWORD on this server before using production mode."
        : "Sign in to your Golf Coach workspace.",
      {
        status: access === "unconfigured" ? 503 : 401,
        headers: {
          "Cache-Control": "no-store",
          ...(access === "unauthorized"
            ? {
                "WWW-Authenticate": 'Basic realm="Golf Coach", charset="UTF-8"',
              }
            : {}),
        },
      },
    );
  const nonce = btoa(crypto.randomUUID());
  const development = process.env.NODE_ENV === "development";
  const csp = `default-src 'self'; script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${development ? "'unsafe-eval'" : ""}; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self'; media-src 'self' blob:; connect-src 'self' ${development ? "ws://localhost:* ws://127.0.0.1:*" : ""}; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`;
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Referrer-Policy", "no-referrer");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set(
    "Permissions-Policy",
    "camera=(self), microphone=(), geolocation=()",
  );
  response.headers.set("Cache-Control", "no-store");
  return response;
}
export const config = {
  // API routes enforce workspaceAccess themselves. Keep upload streams out of
  // middleware: Next 15 clones/truncates its request body at 10 MiB by default.
  matcher: ["/((?!api/|_next/static|_next/image|favicon.ico).*)"],
};

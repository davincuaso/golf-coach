import {
  isLoopback,
  workspaceAccess,
  type AccessEnvironment,
} from "../workspace-auth.ts";

interface ProxyEnvironment extends AccessEnvironment {
  GOLF_BACKEND_URL?: string;
  GOLF_API_TOKEN?: string;
  GOLF_FRONTEND_ORIGIN?: string;
  GOLF_MAX_VIDEO_BYTES?: string;
  GOLF_REQUEST_TIMEOUT_MS?: string;
}
const jsonError = (status: number, message: string) =>
  Response.json(
    { error: { message } },
    { status, headers: { "Cache-Control": "no-store" } },
  );
export async function proxyAnalysis(
  request: Request,
  env: ProxyEnvironment,
  fetcher: typeof fetch = fetch,
  mode:
    | "analysis"
    | "session"
    | "reconstruction"
    | "shot-import"
    | "ball-track" = "analysis",
): Promise<Response> {
  const access = await workspaceAccess(request, env);
  if (access !== "allowed")
    return new Response(
      access === "unconfigured"
        ? "Workspace access is not configured."
        : "Workspace sign-in is required.",
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
  const origin = request.headers.get("origin");
  const expectedOrigin =
    env.GOLF_FRONTEND_ORIGIN || new URL(request.url).origin;
  // Next's development server can normalize the request URL to localhost even
  // when the browser used 127.0.0.1. Permit only equivalent loopback origins.
  let localAlias = false;
  if (origin && !env.GOLF_FRONTEND_ORIGIN && env.NODE_ENV === "development") {
    try {
      const source = new URL(origin),
        target = new URL(expectedOrigin);
      localAlias =
        source.origin === origin &&
        isLoopback(source.hostname) &&
        isLoopback(target.hostname) &&
        source.port === target.port &&
        source.protocol === target.protocol;
    } catch {
      /* Invalid origins remain forbidden. */
    }
  }
  if (!origin || (origin !== expectedOrigin && !localAlias))
    return jsonError(
      403,
      "This request must come from your Golf Coach workspace.",
    );
  if (!env.GOLF_API_TOKEN)
    return jsonError(
      503,
      "The analysis connection is not configured. Check the server setup guide.",
    );
  const contentType = request.headers.get("content-type") || "";
  const jsonMode = ["session", "reconstruction", "shot-import"].includes(mode);
  if (
    !(jsonMode
      ? /^application\/json(?:;|$)/i.test(contentType)
      : /^multipart\/form-data;\s*boundary=/i.test(contentType)) ||
    contentType.length > 300 ||
    !request.body
  )
    return jsonError(415, "Choose a video file to analyze.");
  const configuredMax = Number(env.GOLF_MAX_VIDEO_BYTES || 262144000);
  if (
    !Number.isSafeInteger(configuredMax) ||
    configuredMax < 1024 ||
    configuredMax > 524288000
  )
    return jsonError(503, "The upload limit is not configured correctly.");
  const maxBytes =
    mode === "reconstruction"
      ? 16 * 1048576
      : jsonMode
        ? 1048576
        : configuredMax + 1048576;
  const length = request.headers.get("content-length");
  if (
    length !== null &&
    (!/^\d{1,20}$/.test(length) || Number(length) > maxBytes)
  )
    return jsonError(413, "This video exceeds the upload limit.");
  let upstream: URL;
  try {
    upstream = new URL(
      {
        analysis: "/api/v1/analyses",
        session: "/api/v1/sessions",
        reconstruction: "/api/v1/reconstructions",
        "shot-import": "/api/v1/shot-imports",
        "ball-track": "/api/v1/ball-tracks",
      }[mode],
      env.GOLF_BACKEND_URL || "http://127.0.0.1:8000",
    );
    if (
      (upstream.protocol !== "https:" &&
        !(upstream.protocol === "http:" && isLoopback(upstream.hostname))) ||
      upstream.username ||
      upstream.password
    )
      return jsonError(
        503,
        "The analysis connection is not configured correctly.",
      );
  } catch {
    return jsonError(
      503,
      "The analysis connection is not configured correctly.",
    );
  }
  const timeout = Number(env.GOLF_REQUEST_TIMEOUT_MS || 300000);
  if (!Number.isFinite(timeout) || timeout < 1000 || timeout > 900000)
    return jsonError(
      503,
      "The analysis time limit is not configured correctly.",
    );
  let bytes = 0;
  let tooLarge = false;
  const stream = request.body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        bytes += chunk.byteLength;
        if (bytes > maxBytes) {
          tooLarge = true;
          controller.error(new Error("Upload limit exceeded"));
        } else controller.enqueue(chunk);
      },
    }),
  );
  const timeoutSignal = AbortSignal.timeout(timeout);
  const signal = AbortSignal.any([request.signal, timeoutSignal]);
  const headers = new Headers({
    "Content-Type": contentType,
    Authorization: `Bearer ${env.GOLF_API_TOKEN}`,
  });
  try {
    const options: RequestInit & { duplex: "half" } = {
      method: "POST",
      headers,
      body: stream,
      signal,
      cache: "no-store",
      redirect: "error",
      duplex: "half",
    };
    const response = await fetcher(upstream, options);
    if (!response.ok) {
      await response.body?.cancel();
      const messages: Record<number, string> = {
        400: "The upload could not be read. Try selecting the video again.",
        401: "The server could not connect to the analysis service.",
        403: "The analysis service refused this connection.",
        413: "The video exceeds the configured upload limit.",
        415: "This video format is not supported.",
        422:
          mode === "reconstruction"
            ? "Check calibration scale/orientation, matching resolution, fixed-camera confirmation, original timing, and synchronization within 10 ms. Reanalyze views created before this update."
            : mode === "shot-import"
              ? "Check the import template, one shot per Swing ID, explicit units/methods, numeric ranges, and timezone-aware timestamps."
              : mode === "ball-track"
                ? "Check the fixed camera, visible ball seed, seed time, radius, and source analysis."
                : "The swing could not be analyzed. Check the clip length, camera view, swing markers, and subject selection.",
        503: "Analysis is busy or the pose model is not ready. Try again shortly.",
        504: "Analysis took too long. Try a shorter clip or a smaller pose model.",
      };
      return jsonError(
        response.status,
        messages[response.status] ||
          "The analysis service could not complete this swing.",
      );
    }
    if (!response.headers.get("content-type")?.includes("application/json")) {
      await response.body?.cancel();
      return jsonError(
        502,
        "The analysis service returned an unreadable result.",
      );
    }
    return new Response(response.body, {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    if (tooLarge) return jsonError(413, "The video exceeds the upload limit.");
    if (timeoutSignal.aborted)
      return jsonError(504, "Analysis took too long. Try a shorter clip.");
    if (request.signal.aborted) return jsonError(499, "Analysis was canceled.");
    return jsonError(
      502,
      "The analysis service is unavailable. Check that the backend is running.",
    );
  }
}

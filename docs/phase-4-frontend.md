# Phase 4: Swing Lab and coaching settings

This is a Next.js **15.5.29** App Router application, using React 19, TypeScript,
Tailwind CSS 4, and runtime validation with Zod. It connects to the existing
single-tenant FastAPI service. No paid service is required for rule-based analysis.

## Start locally

Use Python 3.12 and Node.js 24. Complete the backend setup and download a trusted
pose checkpoint as described in the root README. From the repository root:

```sh
python backend/scripts/init_env.py
cd frontend
npm ci
npm run setup:local
npm run dev -- --hostname 127.0.0.1
```

In another terminal, from the root, start the backend:

```sh
cd backend
../.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Open <http://127.0.0.1:3000>. The setup helper copies the backend bearer token to
an ignored, mode-0600 `frontend/.env.local`. It does not display it, overwrite an
existing file, or copy Supabase credentials. A custom backend token format must
use the URL-safe characters accepted by the backend. After changing environment
files, restart Next.js. If you rotate the backend token, update the frontend token
as well; rerunning setup preserves existing files.

## Browser flow

1. Upload an MP4, MOV, WebM, AVI, or M4V, or open the camera and record video
   without audio. Recordings stop automatically at 30 seconds. The upload limit is
   100 MiB; the backend also checks decoded duration, format, and resource limits.
2. Choose the camera perspective. Posture screening requires a down-the-line view.
3. Optionally add all three start/top/impact markers in seconds. Scrub the native
   player and use the current-time buttons. Leave all blank for event estimation.
   For multiple people, enter a normalized point inside the golfer in frame one.
4. Analyze. Actual transfer progress is followed by an indeterminate processing
   state with elapsed time. Cancel aborts the browser request. Server processing
   may continue until disconnect handling or its worker deadline ends it.
5. Review the video, timestamp-aligned skeleton, current-frame angles, metrics,
   charts, observations, and drills. Save results exports the response JSON without
   credentials. Videos and results are not automatically retained by the frontend.

Camera capture needs HTTPS or localhost and explicit browser permission. Camera
tracks are stopped on completion, close, source change, or unmount. MP4/H.264 or
WebM generally provides browser playback; accepting an extension does not guarantee
that the browser or OpenCV supports its codec. A playback warning does not prevent
backend analysis. Browser recordings may lack useful duration metadata before
decoding; backend duration validation remains authoritative.

Pose coordinates use image pixels, and overlays use the same containment transform
as the video. Interpolated landmarks are amber. Missing points are omitted. If the
browser's video aspect ratio differs from the pose metadata, the overlay is hidden
with an explanation. Pose lookup uses decoded timestamps rather than assuming
constant FPS. Chart lines stop at missing samples. Unknown metrics show a dash,
not zero. Wrist speed is expressed in torso lengths per second, not clubhead speed.

## BYOK lifecycle

`src/state/ApiKeyContext.tsx` loads settings after hydration, keeping server-rendered
HTML free of the key. Local storage key `golf-coach:byok:v1` contains a versioned
key/toggle object. The default is AI off. Changes synchronize across tabs.
Malformed saved settings disable synthesis. Blocked or full storage triggers a
visible message and retains changes only in memory. Forget removes only this
application's stored object and turns AI off.

**Local storage is persistent, readable by same-origin JavaScript, and not an
encrypted secret vault.** It also persists after signing out of workspace Basic
auth. Use a personal device, avoid untrusted scripts/extensions, and forget the key
when finished. Encryption with a key bundled into the same app would not protect
against a script running on that origin. Memory-only storage or a managed vault
can replace this persistence strategy for stricter deployments.

The browser sends `X-OpenAI-API-Key` only when the analysis option `llm_enabled` is
true. The key is never put in a URL, form field, metric result, or model prompt.
The Next.js route forwards it to FastAPI over the configured server connection;
the existing backend uses a request-scoped OpenAI client. Rule-only feedback is
available with AI off, skipped, or unavailable. An existing AI narrative is hidden
when the current setting is off. Enabling AI later requires analyzing again to
obtain a narrative for a result that was originally rule-only.

## Server boundary and deployment

`app/api/v1/analyses/route.ts` is a Node.js route handler, not a client-side call
to FastAPI. It streams multipart data to the fixed backend endpoint, injects the
server bearer token, limits bytes even without Content-Length, applies deadlines,
and returns sanitized errors. Browser cookies, Basic credentials, and upstream
cookies are not forwarded. The route independently rechecks authentication, so
middleware is not the only authorization boundary.

Environment variables are server-only; never rename them with `NEXT_PUBLIC_`:

- `GOLF_BACKEND_URL`: defaults to `http://127.0.0.1:8000`. Remote connections must
  use HTTPS. This is operator configuration, never user input.
- `GOLF_API_TOKEN`: must match the backend bearer token.
- `GOLF_MAX_VIDEO_BYTES`: defaults to 104857600, plus 1 MiB multipart allowance.
  The current browser UI permits at most 100 MiB regardless of a larger server cap.
- `GOLF_REQUEST_TIMEOUT_MS`: defaults to 300000; align with backend worker,
  provider, and ingress limits. The browser times out after 310 seconds.
- `GOLF_WEB_USERNAME`: workspace Basic auth username; default `coach`.
- `GOLF_WEB_PASSWORD`: at least 16 characters. Required in production and for
  non-loopback development. Missing configuration fails closed with HTTP 503.
- `GOLF_FRONTEND_ORIGIN`: set to the exact public origin, such as
  `https://golf.example.com`, with no trailing slash. Configure it behind a reverse
  proxy so same-origin checks match the browser's public HTTPS origin.

Development bypasses workspace auth only for loopback request URLs. Next's local
`localhost`/`127.0.0.1` normalization is allowed only for matching scheme and port
in development when no explicit origin is configured. Production checks are exact.

Use HTTPS before deploying this application. Set workspace credentials privately,
then run `npm run build` and `npm start`. The nonce-based CSP requires dynamic
rendering and permits only the app's own scripts. Pages and analysis responses are
marked no-store. Configure trusted hosts, ingress upload/deadline limits, rate
limits, and credential/body redaction in proxies and APM. Do not cache authenticated
HTML or results. The maximum route duration requested is 300 seconds; many hosting
plans impose smaller upload/time limits. Use a Node server with adequate limits
for this synchronous pipeline, or add durable background jobs for those hosts.

This is a password-protected personal workspace, not per-user identity, sessions,
storage ownership, or billing. Provisioning browser direct-to-bucket uploads and
signed object policies remains separate integration work. The backend's private
Supabase object route is documented in Phase 3. Pro-video comparison is also not
part of this dashboard; use footage and pose data that you have rights to before
adding a reference library.

## Verification

```sh
npm test
npm run typecheck
npm run build
```

Tests cover storage persistence/reset/corruption, validation, dynamic BYOK headers,
off-mode omission, abort, response schema checks, independent server auth, origins,
stream limits, error redaction, marker ordering, variable-rate pose lookup, and
chart gaps. The production build includes Next's framework/type checks.

For a real Next.js → FastAPI → YOLO smoke test, first run the backend's
`scripts/smoke_pose.py` to prepare its ignored sample clip and small model. Start
both development servers, then run `npm run smoke:web` in `frontend/`. It validates
24 pose/chart frames with AI disabled. The still sample is a wiring check, not a
golf biomechanics validation. Physical camera/browser codec combinations and a
live user OpenAI account require device/provider-specific acceptance testing.

## File map

```text
frontend/
├── scripts/
│   ├── configure-local.mjs
│   └── smoke-web.mjs
├── src/
│   ├── app/
│   │   ├── api/v1/analyses/route.ts
│   │   ├── settings/page.tsx
│   │   ├── error.tsx
│   │   ├── not-found.tsx
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── AppShell.tsx
│   │   ├── SwingWorkspace.tsx
│   │   ├── capture/{CapturePanel,VideoUpload,VideoRecorder}.tsx
│   │   ├── analysis/{SwingVideoPlayer,PoseOverlay}.tsx
│   │   ├── analysis/{KinematicsChart,KinematicsPanel,CoachingFeedback}.tsx
│   │   └── ui/Icon.tsx
│   ├── lib/
│   │   ├── api-types.ts
│   │   ├── analysis-client.ts
│   │   ├── capture.ts
│   │   ├── settings-storage.ts
│   │   ├── visualization.ts
│   │   ├── workspace-auth.ts
│   │   └── server/analysis-proxy.ts
│   ├── state/ApiKeyContext.tsx
│   └── middleware.ts
└── tests/{settings,upload,proxy,visualization}.test.ts
```

Primary references: [Next.js 15 route handlers](https://nextjs.org/docs/15/app/api-reference/file-conventions/route),
[Next.js 15 CSP](https://nextjs.org/docs/15/app/guides/content-security-policy),
[MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder), and
[localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage).

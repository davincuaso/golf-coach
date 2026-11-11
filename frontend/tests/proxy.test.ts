import { test } from "node:test";
import assert from "node:assert/strict";
import { proxyAnalysis } from "../src/lib/server/analysis-proxy.ts";
import { workspaceAccess } from "../src/lib/workspace-auth.ts";
const env = {
  NODE_ENV: "development",
  GOLF_API_TOKEN: "server-token-test-only",
};
function request(
  headers: Record<string, string> = {},
  body: BodyInit = "--test\r\n",
): Request {
  return new Request("http://localhost:3000/api/v1/analyses", {
    method: "POST",
    headers: {
      origin: "http://localhost:3000",
      "content-type": "multipart/form-data; boundary=test",
      ...headers,
    },
    body,
    duplex: "half",
  } as RequestInit);
}
test("proxy strips retired AI headers and forwards only server authorization", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(String(url), "http://127.0.0.1:8000/api/v1/analyses");
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("authorization"), "Bearer server-token-test-only");
    assert.equal(headers.get("X-OpenAI-API-Key"), null);
    assert.equal(headers.get("cookie"), null);
    assert.equal(headers.get("origin"), null);
    await new Response(init?.body).arrayBuffer();
    return Response.json(
      { prompt_payload: "local prompt" },
      { headers: { "set-cookie": "private=secret" } },
    );
  };
  const response = await proxyAnalysis(
    request({
      cookie: "private=not-forwarded",
      authorization: "Basic browser-credentials",
      "X-OpenAI-API-Key": "obsolete invalid key",
    }),
    env,
    fetcher,
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("set-cookie"), null);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), { prompt_payload: "local prompt" });
});
test("authentication is enforced inside the route, independent of middleware", async () => {
  const production = {
    NODE_ENV: "production",
    GOLF_WEB_PASSWORD: "test-password-123456",
    GOLF_WEB_USERNAME: "coach",
  };
  assert.equal(await workspaceAccess(request(), production), "unauthorized");
  assert.equal(
    await workspaceAccess(
      request({ authorization: `Basic ${btoa("coach:test-password-123456")}` }),
      production,
    ),
    "allowed",
  );
  assert.equal(
    await workspaceAccess(
      request({ authorization: `Basic ${btoa("coach:wrong")}` }),
      production,
    ),
    "unauthorized",
  );
  assert.equal(
    await workspaceAccess(request(), { NODE_ENV: "production" }),
    "unconfigured",
  );
  const response = await proxyAnalysis(
    request(),
    { ...env, ...production },
    async () => {
      throw new Error("Must not reach backend");
    },
  );
  assert.equal(response.status, 401);
});
test("Next development loopback normalization is allowed, but explicit origins stay exact", async () => {
  const fetcher: typeof fetch = async (_, init) => {
    await new Response(init?.body).arrayBuffer();
    return Response.json({});
  };
  assert.equal(
    (
      await proxyAnalysis(
        request({ origin: "http://127.0.0.1:3000" }),
        env,
        fetcher,
      )
    ).status,
    200,
  );
  assert.equal(
    (
      await proxyAnalysis(
        request({ origin: "http://127.0.0.1:3001" }),
        env,
        fetcher,
      )
    ).status,
    403,
  );
  assert.equal(
    (
      await proxyAnalysis(
        request({ origin: "http://127.0.0.1:3000" }),
        { ...env, GOLF_FRONTEND_ORIGIN: "http://localhost:3000" },
        fetcher,
      )
    ).status,
    403,
  );
});
test("cross-origin and oversized requests never reach the worker", async () => {
  const fetcher: typeof fetch = async () => {
    throw new Error("Must not reach backend");
  };
  for (const [headers, status] of [
    [{ origin: "https://elsewhere.test" }, 403],
    [{ "content-length": "999999999" }, 413],
    [{ "content-type": "text/plain" }, 415],
  ] as [Record<string, string>, number][])
    assert.equal(
      (await proxyAnalysis(request(headers), env, fetcher)).status,
      status,
    );
});
test("actual streamed bytes are bounded even without Content-Length", async () => {
  const fetcher: typeof fetch = async (_, init) => {
    await new Response(init?.body).arrayBuffer();
    return Response.json({});
  };
  const response = await proxyAnalysis(
    request({}, new Uint8Array(1049601)),
    { ...env, GOLF_MAX_VIDEO_BYTES: "1024" },
    fetcher,
  );
  assert.equal(response.status, 413);
});
test("provider errors and private configuration never appear in client error text", async () => {
  const a = await proxyAnalysis(
    request(),
    env,
    async () => new Response("secret-provider-key", { status: 422 }),
  );
  assert.equal(a.status, 422);
  assert.doesNotMatch(await a.text(), /secret-provider-key/);
  const b = await proxyAnalysis(request(), env, async () => {
    throw new Error("secret-server-token");
  });
  assert.equal(b.status, 502);
  assert.doesNotMatch(await b.text(), /secret-server-token/);
  const c = await proxyAnalysis(request(), {
    ...env,
    GOLF_BACKEND_URL: "http://remote.test",
  });
  assert.equal(c.status, 503);
});

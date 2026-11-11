Phase 4: `ApiKeyContext.tsx` will own the BYOK key and LLM enabled toggle.
Default LLM OFF. Keep the key in memory only; refreshing clears it. Do not use
localStorage, sessionStorage, cookies, URLs, persistence middleware or analytics.
The browser must still access the key to send it; memory storage is not protection
against XSS. Use HTTPS, an explicit backend origin and a restrictive CSP.

Send the key only for an explicitly enabled coaching request. The request and
response must bypass caches, and logs must redact the credential. A backend must
never echo it. The settings UI and provider are deliberately deferred to Phase 4.

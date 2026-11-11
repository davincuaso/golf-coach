# Browser settings

`ApiKeyContext.tsx` hydrates versioned localStorage preferences on mount and
synchronizes changes across tabs. AI is off by default. Storage failures show a
warning and use memory for the current page. Forget removes the stored object.

localStorage is readable by same-origin JavaScript and is not an encrypted vault.
No backend server token belongs in this context. See the key lifecycle and
server-boundary documentation in [Phase 4](../../../docs/phase-4-frontend.md).

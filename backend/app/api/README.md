Phase 3 is implemented in `routes.py` and `middleware.py`. Every analysis route
requires the backend bearer token before request parsing. OpenAI BYOK headers are
optional and request-scoped. See `../../../docs/phase-3-api.md` for contracts,
configuration, limits and the current single-tenant authorization boundary.

# API endpoints

Every `/api/v1/*` endpoint requires the backend bearer token before request parsing.
Uploads, private storage objects, and existing pose JSON all produce metrics,
rule-based coaching, and a locally generated `prompt_payload`. There is no AI
provider key header, opt-in toggle, or synthesis request.

See [the API guide](../../../docs/phase-3-api.md) and
[prompt workflow](../../../docs/prompt-workflow.md).

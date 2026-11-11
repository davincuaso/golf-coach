# Manual ChatGPT coaching workflow

1. Record or upload a swing and run analysis.
2. Review the metrics, quality notes, faults, and drills.
3. In **AI Coaching Prompt**, click **Copy to Clipboard**.
4. Click **Open ChatGPT**, paste the prompt into your conversation, and send it
   when ready. No automatic submission or API billing is involved in this app.

## Response contract

All three FastAPI analysis routes return:

```json
{
  "analysis_id": "generated-analysis-id",
  "kinematics": {},
  "coaching": {},
  "prompt_payload": "Act as a master golf professional...",
  "pose": null
}
```

The abbreviated objects above contain the existing typed metric/rule reports in
a real response. `pose` contains validated frame data when `include_pose` is true.
`prompt_payload` is always a nonempty string, including for insufficient tracking
or no flagged faults. The frontend validates this field before displaying results.

## Prompt content and bounds

`backend/app/coaching/llm_synthesizer.py` retains its requested filename but now
exports the synchronous `generate_coaching_prompt(metrics, rules) -> str` function.
It has no provider SDK import, network call, API key, model selection, or timeout.

The prompt asks for observations supported by exact values, at most one explicitly
tentative root-cause hypothesis, one practice priority, up to two catalog drills,
and a short next-swing plan. It states the limits of 2D measurements, estimated
markers, missing data, camera perspective, and wrist-speed units. No-fault reports
must not become invented faults or a claim that the swing is perfect.

The JSON includes all original scalar kinematics, fault evidence, warnings,
notices, and drill instructions. Raw trace values are compact rows with named
columns. Short traces are complete. Long traces include 121 uniformly indexed
samples plus neighbors of the three swing events (at most 127 rows). The JSON
discloses the source count, included count, sampling method, and location of the
complete trace. Values retain original precision and nulls; the generator does
not interpolate, round, or replace unknown values with zero. Sampling may omit
gaps/extrema, so the instructions defer quality and fault judgments to full-report
aggregates and rule evidence. Complete `kinematics.series` remains in the response
and exported JSON.

No video, full pose landmarks, filename, storage path, request headers, or backend
credentials enter this prompt. Opening ChatGPT does not transmit the prompt. The
user controls when to paste/send measurements to their chosen chat.

## Migration

- Remove the `openai` dependency and AI model/timeout environment configuration.
  If upgrading an existing environment, run `python -m pip uninstall openai`.
- Stop sending `llm_enabled`; unknown options now receive HTTP 422.
- Read `prompt_payload` instead of `llm` in API clients. Update backend and frontend
  together, and reanalyze old exported results to obtain the new prompt field.
- No provider key header is needed. Retired headers are ignored by FastAPI and
  stripped by Next.js. They are never included in the generated prompt.
- The context and `/settings` page are removed. On mount, the frontend attempts to
  delete only `golf-coach:byok:v1` from localStorage without reading its value.
  If browser storage is blocked, clear this site's data through browser settings.
- Backend bearer auth and production workspace Basic auth still protect analysis
  resources; those server credentials are unrelated to AI provider access.

Restart both services after the update. The CLI and smoke-test clients now use the
new response shape, without AI flags or credential prompts.

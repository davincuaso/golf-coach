# Coaching pipeline

- `kinematics.py`: camera-dependent posture and timestamp-based tempo measurements.
- `rule_engine.py`: versioned observations, evidence, notices, and drill catalog.
- `llm_synthesizer.py`: local `generate_coaching_prompt(metrics, rules)` formatting.
- `schemas.py`: typed contracts, including the required `prompt_payload` response.

Prompt generation requires no AI SDK, credentials, or network access. Full computed
metrics and rule evidence are preserved; long raw traces have an explicitly sampled
preview. See [the prompt workflow](../../../docs/prompt-workflow.md).

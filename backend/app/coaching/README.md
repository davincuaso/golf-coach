Implemented Phase 3 Hybrid Coaching Engine:

- `kinematics.py`: event detection, tempo and camera-aware 2D metrics.
- `rule_engine.py`: deterministic flags, evidence and rule versioning.
- `llm_synthesizer.py`: optional OpenAI narrative using validated rule evidence.
- `schemas.py`: validated input and output contracts, including quality flags.

Only validated metrics may enter coaching rules. Missing values stay unknown.
The rules work without an OpenAI key. A request-scoped key must never enter logs,
storage, job payloads, analytics, exception output, or a shared OpenAI client.
Do not infer real clubhead speed from body pose or uncalibrated image coordinates.
Automatic events are explicitly estimated wrist proxies; supplied video markers
remain the preferred input for tempo and posture screening.

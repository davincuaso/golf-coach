"""Real FastAPI upload -> isolated YOLO process -> coaching smoke test with a locally generated coaching prompt.

Run scripts/smoke_pose.py first, then from backend/:
    ../.venv/bin/python scripts/smoke_api.py
"""

import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    source, previous = ROOT / "data/smoke.avi", ROOT / "data/smoke.analysis.json"
    weights = ROOT / "backend/models/yolov8n-pose.pt"
    if not all(path.is_file() for path in (source, previous, weights)):
        raise RuntimeError("Run scripts/smoke_pose.py to create the local sample and model first.")
    subject = json.loads(previous.read_text())["processing"]["config"]["subject_point"]
    token = secrets.token_urlsafe(32)
    app = create_app(Settings(api_token=token, pose_weights=weights, pose_image_size=640))
    with TestClient(app) as client, source.open("rb") as video:
        response = client.post(
            "/api/v1/analyses",
            headers={"Authorization": f"Bearer {token}"},
            files={"video": ("sample.avi", video, "video/x-msvideo")},
            data={"options": json.dumps({"subject_point": subject})},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"API smoke test failed: HTTP {response.status_code}: {response.text}"
            )
        payload = response.json()
        assert payload["pose"]["video"]["frame_count"] == 24
        assert len(payload["kinematics"]["series"]) == 24
        assert "master golf professional" in payload["prompt_payload"]
        assert "llm" not in payload
        assert payload["kinematics"]["events"] is None  # A still image is not a swing.
        assert response.headers["Cache-Control"] == "no-store"
        repeated = client.post(
            "/api/v1/coaching",
            headers={"Authorization": f"Bearer {token}"},
            json={"vision": payload["pose"], "options": {"include_pose": False}},
        )
        assert repeated.status_code == 200 and repeated.json()["pose"] is None
    print(
        "Phase 3 smoke passed: authenticated upload, real isolated YOLO, 24 pose/chart frames, rules, local coaching prompt, saved-pose coaching."
    )


if __name__ == "__main__":
    main()

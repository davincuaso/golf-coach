"""Analyze a local video and save metrics, rules, and a manual ChatGPT prompt."""

import argparse
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main():
    import httpx

    from app.coaching.schemas import AnalysisOptions, SwingEvents
    from app.config import Settings
    from app.vision.vision_processor import write_json_atomic

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument(
        "--view", choices=["down_the_line", "face_on", "unknown"], default="unknown"
    )
    parser.add_argument("--events", type=float, nargs=3, metavar=("START", "TOP", "IMPACT"))
    parser.add_argument("--subject-point", type=float, nargs=2)
    parser.add_argument("--output", type=Path, default=BACKEND.parent / "data/api.analysis.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error("Choose an existing local video.")
    if args.output.resolve() == args.video.resolve():
        parser.error("Output cannot replace the input video.")
    if args.output.exists() and not args.overwrite:
        parser.error("Output exists; choose another path or pass --overwrite.")
    settings = Settings()
    events = (
        SwingEvents(
            start_seconds=args.events[0], top_seconds=args.events[1], impact_seconds=args.events[2]
        )
        if args.events
        else None
    )
    options = AnalysisOptions(
        camera_view=args.view,
        events=events,
        subject_point=tuple(args.subject_point) if args.subject_point else None,
    )
    headers = {"Authorization": "Bearer " + settings.api_token.get_secret_value()}
    with (
        httpx.Client(
            timeout=settings.worker_timeout_seconds + 90,
            trust_env=False,
        ) as client,
        args.video.open("rb") as video,
    ):
        response = client.post(
            "http://127.0.0.1:8000/api/v1/analyses",
            headers=headers,
            files={"video": (args.video.name, video, "application/octet-stream")},
            data={"options": options.model_dump_json()},
        )
    if response.status_code != 200:
        print(f"Analysis failed (HTTP {response.status_code}): {response.text}", file=sys.stderr)
        return 1
    payload = response.json()
    write_json_atomic(payload, args.output, overwrite=args.overwrite)
    print(f"Saved analysis and coaching prompt to {args.output}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

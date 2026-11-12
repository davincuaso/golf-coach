"""Download a pinned public ONNX model; never uploads media or executes hub code."""

import argparse
import hashlib
from pathlib import Path
import tempfile

import httpx

URL = "https://huggingface.co/notjulietxd/golf-ball-tracker/resolve/d8c3317b211bb7c0592d97111d79519a610fd775/best.onnx"
SHA256 = "9e948135c9898c2b0e4194fa992308a0bbb478e21f6407dda12cb49e3e91ac22"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "models/golf-ball-yolov8n.onnx",
    )
    args = parser.parse_args()
    target = args.output
    if target.exists():
        with target.open("rb") as handle:
            valid = hashlib.file_digest(handle, "sha256").hexdigest() == SHA256
        if not valid:
            parser.error("Existing file has a different checksum; choose a new path.")
        print("Pinned model already present and verified.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as folder:
        temp = Path(folder) / "model.onnx"
        digest = hashlib.sha256()
        size = 0
        with httpx.stream("GET", URL, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            with temp.open("xb") as handle:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 20 * 1024 * 1024:
                        raise ValueError("Unexpected model size.")
                    digest.update(chunk)
                    handle.write(chunk)
        if digest.hexdigest() != SHA256:
            raise ValueError("Model checksum mismatch.")
        # Exclusive creation avoids replacing an existing model after a race.
        with target.open("xb") as output, temp.open("rb") as source:
            import shutil

            shutil.copyfileobj(source, output)
    print(
        "Installed checksum-verified ONNX golf-ball detector. Restart the backend. See docs/open-source-ball-models.md for validation and source limitations."
    )


if __name__ == "__main__":
    main()

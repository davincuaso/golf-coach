"""Create a private local server configuration without printing its bearer token."""

import os
from pathlib import Path
import secrets

BACKEND = Path(__file__).resolve().parents[1]


def main():
    destination = BACKEND / ".env"
    template = (BACKEND / ".env.example").read_text()
    configured = template.replace(
        "GOLF_API_TOKEN=replace-with-a-random-token-at-least-24-characters",
        "GOLF_API_TOKEN=" + secrets.token_urlsafe(32),
        1,
    )
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print("backend/.env already exists; preserved its configuration.")
        return
    with os.fdopen(descriptor, "w") as handle:
        handle.write(configured)
    print("Created backend/.env with a random server token. The token was not printed.")


if __name__ == "__main__":
    main()

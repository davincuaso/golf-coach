"""Signed, expiring summaries, never a replacement for endpoint authentication."""

import base64
import hashlib
import hmac
import json
import time

from app.errors import ServiceError


def sign_evidence(
    kind: str, swing_ids: list[str], analysis_ids: list[str], evidence: dict, secret: str
) -> str:
    data = {
        "kind": kind,
        "swing_ids": swing_ids,
        "analysis_ids": analysis_ids,
        "evidence": evidence,
        "issued": int(time.time()),
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(data, allow_nan=False, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(
        secret.encode(), ("golf-evidence-v1:" + encoded).encode(), hashlib.sha256
    ).hexdigest()
    token = encoded + "." + signature
    if len(token) > 64000:
        raise ServiceError(
            422, "evidence_too_large", "Choose at most eight shots for this session."
        )
    return token


def verify_evidence(token: str, secret: str) -> dict:
    try:
        encoded, signature = token.split(".")
        expected = hmac.new(
            secret.encode(), ("golf-evidence-v1:" + encoded).encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if not -60 <= time.time() - data["issued"] <= 86400:
            raise ValueError
        return data
    except Exception:
        raise ServiceError(
            422,
            "invalid_evidence",
            "Additional evidence is invalid or expired. Run that evidence check again.",
        ) from None

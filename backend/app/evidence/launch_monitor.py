"""Explicit vendor-neutral imports. Never guess units or measurement provenance."""

from __future__ import annotations

import csv
from datetime import datetime
import io
import json
from typing import Literal

from pydantic import Field, FiniteFloat, model_validator

from app.coaching.schemas import StrictModel
from app.errors import ServiceError

METHODS = {"measured", "device_calculated", "manual", "unknown"}
# canonical unit, inclusive canonical range
METRICS = {
    "ball_speed": ("m/s", 0, 120),
    "launch_angle": ("deg", -20, 90),
    "launch_direction": ("deg", -90, 90),
    "spin_rate": ("rpm", 0, 20000),
    "spin_axis": ("deg", -180, 180),
    "carry": ("m", 0, 500),
    "total_distance": ("m", 0, 600),
    "apex": ("m", 0, 150),
    "offline": ("m", -200, 200),
}
FACTORS = {
    "m": 1,
    "yd": 0.9144,
    "ft": 0.3048,
    "m/s": 1,
    "mph": 0.44704,
    "km/h": 1 / 3.6,
    "deg": 1,
    "rpm": 1,
}


class ShotIntent(StrictModel):
    carry_min_m: FiniteFloat | None = Field(default=None, ge=0, le=500)
    carry_max_m: FiniteFloat | None = Field(default=None, ge=0, le=500)
    launch_direction_min_deg: FiniteFloat = Field(default=-3, ge=-90, le=90)
    launch_direction_max_deg: FiniteFloat = Field(default=3, ge=-90, le=90)
    offline_tolerance_m: FiniteFloat = Field(default=15, ge=0, le=200)
    desired_shape: Literal["unspecified", "straight", "draw", "fade"] = "unspecified"
    handedness: Literal["right", "left"] = "right"
    straight_spin_axis_tolerance_deg: FiniteFloat = Field(default=5, ge=0, le=30)

    @model_validator(mode="after")
    def ordered(self):
        if (
            (self.carry_min_m is None) != (self.carry_max_m is None)
            or (self.carry_min_m is not None and self.carry_min_m > self.carry_max_m)
            or self.launch_direction_min_deg > self.launch_direction_max_deg
        ):
            raise ValueError("Intent ranges must be ordered.")
        return self


class ShotImportRequest(StrictModel):
    format: Literal["csv", "json"]
    content: str = Field(min_length=1, max_length=500_000)
    device: str = Field(min_length=1, max_length=80)
    positive_direction: Literal["right", "left"]
    positive_spin_axis_curve: Literal["right", "left", "unknown"] = "unknown"
    conditions: Literal["outdoor", "indoor", "normalized", "unknown"] = "unknown"
    intent: ShotIntent


class ShotMeasurement(StrictModel):
    value: FiniteFloat
    unit: str
    method: Literal["measured", "device_calculated", "manual", "unknown"]
    original_value: FiniteFloat
    original_unit: str


class ShotCheck(StrictModel):
    metric: str
    status: Literal["within_intent", "outside_intent", "unavailable"]
    explanation: str


class ImportedShot(StrictModel):
    shot_id: str
    swing_id: str
    recorded_at: str | None
    metrics: dict[str, ShotMeasurement]
    checks: list[ShotCheck]


class ShotImportResponse(StrictModel):
    version: Literal["1.0"] = "1.0"
    device: str
    conditions: str
    shots: list[ImportedShot]
    intent: ShotIntent
    notices: list[str]
    evidence_token: str = ""


def _reject(message):
    raise ServiceError(422, "invalid_shot_import", message)


def import_shots(request: ShotImportRequest) -> ShotImportResponse:
    allowed = {"shot_id", "swing_id", "recorded_at"} | {
        key + suffix for key in METRICS for suffix in ("", "_unit", "_method")
    }
    try:
        if request.format == "json":
            rows = json.loads(request.content)
            if not isinstance(rows, list):
                _reject("JSON must contain an array of shot rows using the documented columns.")
        else:
            reader = csv.DictReader(io.StringIO(request.content.lstrip("\ufeff")), strict=True)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                _reject("CSV headers must be unique.")
            rows = list(reader)
    except (ValueError, csv.Error):
        _reject("The import could not be parsed. Use the provided CSV/JSON template.")
    if not 1 <= len(rows) <= 8:
        _reject("Import one to eight shots, explicitly matched to swing IDs.")
    shots, identifiers, swings = [], set(), set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) - allowed
            or any(not isinstance(key, str) for key in row)
        ):
            _reject("Unknown columns or malformed rows. Map vendor exports to the template first.")
        import re

        shot_id, swing_id = row.get("shot_id"), row.get("swing_id")
        if (
            not isinstance(shot_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", shot_id)
            or not isinstance(swing_id, str)
            or not re.fullmatch(r"[A-Za-z0-9 _-]{1,40}", swing_id)
            or not swing_id.strip()
            or shot_id in identifiers
            or swing_id in swings
        ):
            _reject(
                "Each shot needs unique shot and swing IDs. Use one monitor shot per physical swing."
            )
        identifiers.add(shot_id)
        swings.add(swing_id)
        stamp = row.get("recorded_at") or None
        if stamp:
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
                stamp = parsed.isoformat()
            except (TypeError, ValueError, AttributeError):
                _reject("Timestamps require ISO 8601 with a timezone, or an empty field.")
        metrics = {}
        for name, (canonical, lower, upper) in METRICS.items():
            raw = row.get(name)
            if raw is None or raw == "":
                continue
            unit, method = row.get(name + "_unit"), row.get(name + "_method")
            if method is None or method == "":
                method = "unknown"
            legal_units = (
                {"m", "yd", "ft"}
                if canonical == "m"
                else {"m/s", "mph", "km/h"}
                if canonical == "m/s"
                else {canonical}
            )
            if (
                not isinstance(unit, str)
                or unit not in legal_units
                or not isinstance(method, str)
                or method not in METHODS
                or isinstance(raw, bool)
            ):
                _reject(
                    "Every populated measurement needs an explicit compatible unit and valid method."
                )
            try:
                value = original = float(raw)
                value *= FACTORS[unit]
                if name in ("launch_direction", "offline") and request.positive_direction == "left":
                    value *= -1
                if name == "spin_axis" and request.positive_spin_axis_curve == "left":
                    value *= -1
                if not lower <= value <= upper:
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                _reject("A measurement is nonfinite or outside the documented plausible range.")
            metrics[name] = ShotMeasurement(
                value=value,
                unit=canonical,
                method=method,
                original_value=original,
                original_unit=unit,
            )
        if not metrics:
            _reject("Each shot needs at least one populated measurement.")
        intent = request.intent
        checks = []
        for metric, low, high in (
            ("carry", intent.carry_min_m, intent.carry_max_m),
            ("launch_direction", intent.launch_direction_min_deg, intent.launch_direction_max_deg),
            ("offline", -intent.offline_tolerance_m, intent.offline_tolerance_m),
        ):
            measurement = metrics.get(metric)
            known = (
                measurement is not None
                and measurement.method != "unknown"
                and low is not None
                and high is not None
            )
            checks.append(
                ShotCheck(
                    metric=metric,
                    status=(
                        "within_intent" if low <= measurement.value <= high else "outside_intent"
                    )
                    if known
                    else "unavailable",
                    explanation=f"Compared with your {low:g} to {high:g} {METRICS[metric][0]} intent range. Source method: {measurement.method}."
                    if known
                    else "Missing value, unset intent range, or unknown measurement provenance.",
                )
            )
        axis = metrics.get("spin_axis")
        if (
            intent.desired_shape == "unspecified"
            or axis is None
            or axis.method == "unknown"
            or request.positive_spin_axis_curve == "unknown"
        ):
            checks.append(
                ShotCheck(
                    metric="shape_tendency",
                    status="unavailable",
                    explanation="Set a desired shape and provide spin-axis provenance and a verified curve sign convention.",
                )
            )
        else:
            tendency = (
                "straight"
                if abs(axis.value) <= intent.straight_spin_axis_tolerance_deg
                else "fade"
                if (axis.value > 0) == (intent.handedness == "right")
                else "draw"
            )
            checks.append(
                ShotCheck(
                    metric="shape_tendency",
                    status="within_intent"
                    if tendency == intent.desired_shape
                    else "outside_intent",
                    explanation=f"Spin-axis tendency: {tendency}; this is not an observed full-flight shape. Wind and strike conditions may change the actual result.",
                )
            )
        shots.append(
            ImportedShot(
                shot_id=shot_id,
                swing_id=swing_id,
                recorded_at=stamp,
                metrics=metrics,
                checks=checks,
            )
        )
    return ShotImportResponse(
        device=request.device,
        conditions=request.conditions,
        shots=shots,
        intent=request.intent,
        notices=[
            "Imported readings are supplied by you, not independently verified device telemetry. Original units and per-field methods are retained.",
            "Positive launch direction/offline is right of the target. Spin-axis tendency is withheld unless its curve sign convention is explicitly confirmed.",
            "Device-calculated or normalized carry is modelled evidence, not an observed landing. No simulated trajectory is drawn.",
            "Within/outside intent is a comparison with your chosen ranges, not a universal judgement of a correct shot. Missing data remains unknown.",
        ],
    )

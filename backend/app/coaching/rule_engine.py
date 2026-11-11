"""Deterministic, versioned screening rules; independent of OpenAI availability."""

from dataclasses import dataclass
import math

from app.coaching.schemas import Drill, Fault, KinematicsReport, RuleReport

DRILLS = {
    "hip_depth_rehearsal": Drill(
        id="hip_depth_rehearsal",
        name="Hip-depth rehearsal",
        instructions=[
            "Take your address posture with a chair just behind your hips.",
            "Make five slow, club-free turns while maintaining light hip contact with the chair.",
            "Record five half-speed swings from down the line and compare posture through the downswing.",
        ],
    ),
    "tempo_count": Drill(
        id="tempo_count",
        name="Three-count back, one-count down",
        instructions=[
            "Rehearse at half speed while counting three even beats to the top and one beat down.",
            "Repeat ten times with a comfortable motion rather than chasing speed.",
            "Record three swings, mark the phases and check whether the ratio becomes more consistent.",
        ],
    ),
}


@dataclass(frozen=True)
class RuleConfig:
    posture_loss_threshold_deg: float = 10.0
    tempo_min: float = 2.5
    tempo_max: float = 3.5

    def __post_init__(self):
        if (
            not all(
                math.isfinite(v)
                for v in (self.posture_loss_threshold_deg, self.tempo_min, self.tempo_max)
            )
            or self.posture_loss_threshold_deg <= 0
            or not 0 < self.tempo_min < self.tempo_max
        ):
            raise ValueError("Rule thresholds must be finite, positive and ordered.")


def evaluate_rules(metrics: KinematicsReport, config: RuleConfig | None = None) -> RuleReport:
    config = config or RuleConfig()
    faults = []
    notices = [
        "These are configurable coaching observations, not diagnoses or universal swing targets."
    ]
    if metrics.posture_eligible and metrics.max_posture_loss_deg is not None:
        if metrics.max_posture_loss_deg > config.posture_loss_threshold_deg:
            faults.append(
                Fault(
                    code="LOSS_OF_POSTURE",
                    title="Possible loss of posture",
                    severity="moderate",
                    explanation="The torso appeared more upright during the downswing than at address. Check hip depth and camera alignment before changing technique.",
                    evidence={
                        "max_posture_loss_deg": metrics.max_posture_loss_deg,
                        "threshold_deg": config.posture_loss_threshold_deg,
                        "event_source": metrics.event_source or "unknown",
                    },
                    drill_ids=["hip_depth_rehearsal"],
                )
            )
    else:
        notices.append(
            "Posture screening was skipped because camera view or landmark evidence was insufficient."
        )
    if metrics.tempo_ratio is not None and metrics.timing_reliable:
        if not config.tempo_min <= metrics.tempo_ratio <= config.tempo_max:
            faults.append(
                Fault(
                    code="TEMPO_OUTSIDE_REFERENCE",
                    title="Tempo outside the selected reference range",
                    severity="observation",
                    explanation="The backswing-to-downswing duration ratio falls outside the configured practice range. This alone does not identify which phase should change.",
                    evidence={
                        "tempo_ratio": metrics.tempo_ratio,
                        "reference_min": config.tempo_min,
                        "reference_max": config.tempo_max,
                        "event_source": metrics.event_source or "unknown",
                    },
                    drill_ids=["tempo_count"],
                )
            )
    else:
        notices.append("Tempo screening needs usable swing markers and reliable timing.")
    if metrics.event_source == "estimated":
        notices.append("Confirm the estimated swing markers before acting on these observations.")
    if not faults:
        notices.append(
            "No configured threshold was crossed in the available evidence; this is not a complete swing assessment."
        )
    drill_ids = list(dict.fromkeys(drill for fault in faults for drill in fault.drill_ids))
    return RuleReport(
        faults=faults,
        drills=[DRILLS[key].model_copy(deep=True) for key in drill_ids],
        notices=notices,
    )

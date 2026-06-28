"""
Close-probability predictor.

Current implementation is a transparent heuristic (model_ref='heuristic-v1')
so the inference path exists end-to-end TODAY — no waiting for a trained
model. Each adjustment is recorded in Prediction.reasons so the UI/admin
can show *why* a number came out the way it did.

When a real trained model lands:
  - drop a new predict_v2(features) here
  - set model_ref='logreg-v1' (or similar)
  - keep the same return shape; no caller changes.

The Prediction.confidence field is meta — how much input signal the
prediction stood on (NOT the model's calibrated uncertainty). Used by the
UI to dim/show the badge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Prediction:
    probability: float  # 0-1, calibrated as best we can
    confidence: float  # 0-1, how much signal backed it
    reasons: list[str] = field(default_factory=list)
    model_ref: str = "heuristic-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stage_base(stage: str | None) -> float:
    return {"sent": 0.40, "negotiating": 0.65, "won": 1.0, "lost": 0.0}.get(stage or "", 0.35)


def predict_close_probability(features: dict) -> Prediction:
    """Heuristic baseline. Replace with trained model behind same signature."""
    reasons: list[str] = []
    stage = features.get("stage")

    # Terminal stages — short-circuit, no point modelling further.
    if stage == "won":
        return Prediction(probability=1.0, confidence=1.0, reasons=["already won"], model_ref="heuristic-v1")
    if stage == "lost":
        return Prediction(probability=0.0, confidence=1.0, reasons=["already lost"], model_ref="heuristic-v1")

    base = _stage_base(stage)
    reasons.append(f"stage={stage}: base {base:.2f}")

    # Silence penalty — kicks in past 7 days, caps at -0.40.
    days_silent = features.get("days_silent") or 0
    if days_silent > 7:
        penalty = min(0.40, (days_silent - 7) * 0.02)
        base -= penalty
        reasons.append(f"-{penalty:.2f} for {days_silent}d silent")

    # Response history adjustment, if the client has any.
    rate = features.get("response_rate")
    if rate is not None:
        if rate >= 0.70:
            base += 0.15
            reasons.append(f"+0.15 high response rate ({rate:.0%})")
        elif rate <= 0.20:
            base -= 0.20
            reasons.append(f"-0.20 low response rate ({rate:.0%})")

    # Cadence — a fast typical responder is more likely to close.
    cadence = features.get("typical_response_days")
    if cadence is not None and cadence <= 2:
        base += 0.05
        reasons.append(f"+0.05 fast responder ({cadence:.1f}d median)")

    probability = max(0.0, min(1.0, base))

    # Confidence = signal density. Four optional inputs; each filled = +0.25.
    signal_inputs = ("days_silent", "response_rate", "typical_response_days", "outcome_count")
    filled = sum(1 for k in signal_inputs if features.get(k) not in (None, 0))
    confidence = round(filled / len(signal_inputs), 2)

    return Prediction(
        probability=round(probability, 3),
        confidence=confidence,
        reasons=reasons,
        model_ref="heuristic-v1",
    )

"""
Data layer — feature extraction + prediction.

Public API (kept narrow so trained models can swap behind it):
  extract_proposal_features(proposal, memory) -> dict
  predict_close_probability(features)         -> Prediction

The current implementation is a transparent heuristic (Prediction.model_ref
is 'heuristic-v1') with no third-party ML deps. A trained model lands here
later as 'logreg-v1', 'gbt-v1', etc., without changing any caller.
"""

from .features import extract_proposal_features  # noqa: F401
from .predict import Prediction, predict_close_probability  # noqa: F401

__all__ = ["extract_proposal_features", "predict_close_probability", "Prediction"]

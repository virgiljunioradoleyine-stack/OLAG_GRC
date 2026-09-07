"""
Model bundles carry their own provenance.

The audit found committed pickles trained on seven features while the code
emitted ten, and a dashboard cheerfully displaying the stale metadata as if it
were current. Every artefact now records what it was trained on, and loading
checks compatibility rather than trusting that the repository is coherent.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import joblib

MODEL_DIR = "models"
BUNDLE_FORMAT = 3


class ModelIncompatible(RuntimeError):
    """The stored model does not match the current feature contract."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def features_fingerprint(features):
    """Stable hash of the ordered feature list."""
    return hashlib.sha256("|".join(features).encode()).hexdigest()[:12]


@dataclass
class ModelBundle:
    station_id: str
    model_version: str
    feature_version: str
    features: list
    feature_fingerprint: str
    algorithm: str
    hyperparameters: dict
    training_start: str
    training_end: str
    validation_start: str = ""
    validation_end: str = ""
    test_start: str = ""
    test_end: str = ""
    training_rows: int = 0
    validation_rows: int = 0
    test_rows: int = 0
    dataset_version: str = ""
    validation_metrics: dict = field(default_factory=dict)
    test_metrics: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    bundle_format: int = BUNDLE_FORMAT
    estimators: dict = field(default_factory=dict)   # the fitted objects

    def metadata(self):
        d = asdict(self)
        d.pop("estimators", None)
        return d

    def check_compatible(self, features):
        """Raise unless the bundle was fitted on exactly these features."""
        if list(features) != list(self.features):
            raise ModelIncompatible(
                f"{self.station_id}: model expects {len(self.features)} features "
                f"(fingerprint {self.feature_fingerprint}) but the code supplies "
                f"{len(features)} (fingerprint {features_fingerprint(features)}). "
                f"Retrain with scripts/train.py before scoring."
            )
        return True


def bundle_path(station_id, model_dir=MODEL_DIR):
    return os.path.join(model_dir, f"{station_id}.joblib")


def save_bundle(bundle, model_dir=MODEL_DIR):
    os.makedirs(model_dir, exist_ok=True)
    path = bundle_path(bundle.station_id, model_dir)
    tmp = path + ".tmp"
    joblib.dump(bundle, tmp)
    os.replace(tmp, path)
    return path


def load_bundle(station_id, model_dir=MODEL_DIR, features=None):
    path = bundle_path(station_id, model_dir)
    if not os.path.exists(path):
        return None
    bundle = joblib.load(path)
    if getattr(bundle, "bundle_format", 0) != BUNDLE_FORMAT:
        raise ModelIncompatible(
            f"{station_id}: bundle format {getattr(bundle,'bundle_format',None)} "
            f"!= expected {BUNDLE_FORMAT}. Retrain.")
    if features is not None:
        bundle.check_compatible(features)
    return bundle

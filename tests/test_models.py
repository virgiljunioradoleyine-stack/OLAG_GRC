"""Model contract tests: splits, fitting, versioning, compatibility."""
import numpy as np
import pandas as pd
import pytest

from pipeline.features.builder import FEATURE_COLUMNS, build_features
from pipeline.models.anomaly import ANOMALY_FEATURES, AnomalyModel
from pipeline.models.baseline import BASELINE_FEATURES, ExpectedConditionModel
from pipeline.models.splits import SplitSpec, chronological_split, split_summary
from pipeline.models.versioning import (
    ModelBundle, ModelIncompatible, features_fingerprint,
)


# --------------------------------------------------------------- splits ---

def test_chronological_split_is_ordered_and_disjoint():
    df = pd.DataFrame({"date": pd.date_range("2017-01-01", "2026-06-01", freq="15D")})
    tr, va, te = chronological_split(df)
    assert (tr.astype(int) + va.astype(int) + te.astype(int) == 1).all()
    d = df["date"]
    assert d[tr].max() < d[va].min() <= d[va].max() < d[te].min()


def test_split_refuses_an_empty_training_period():
    df = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=10, freq="D")})
    with pytest.raises(ValueError, match="no training data"):
        chronological_split(df, SplitSpec("2017-01-01", "2018-01-01"))


def test_split_summary_reports_all_three_periods():
    df = pd.DataFrame({"date": pd.date_range("2017-01-01", "2026-06-01", freq="15D")})
    s = split_summary(df)
    assert s["train"]["n"] and s["validation"]["n"] and s["test"]["n"]


# ------------------------------------------------------------- baseline ---

def _feature_frame(obs_frame, rain_frame):
    return build_features(obs_frame(1), obs_frame(2, "P04"), obs_frame(3, "P01"), rain_frame)


def test_baseline_fits_and_beats_nothing(obs_frame, rain_frame):
    obs = obs_frame(1)
    X = _feature_frame(obs_frame, rain_frame)
    y = obs["ndti"].to_numpy(float)
    m = ExpectedConditionModel().fit(X.iloc[:120], y[:120])
    metrics = m.evaluate(X.iloc[120:], y[120:])
    assert metrics["n"] > 0 and metrics["mae"] >= 0
    assert m.residual_std_ > 0


def test_baseline_refuses_tiny_training_sets(obs_frame, rain_frame):
    X = _feature_frame(obs_frame, rain_frame)
    y = obs_frame(1)["ndti"].to_numpy(float)
    with pytest.raises(ValueError, match=">= 30"):
        ExpectedConditionModel().fit(X.iloc[:10], y[:10])


def test_baseline_excludes_the_target_from_its_inputs():
    """The baseline must not see ndti or any same-day transform of it."""
    banned = {"ndti", "ndti_delta", "ndti_anom_30d", "seasonal_anomaly",
              "ndti_change_3d", "ndti_change_7d", "red", "red_anom_30d"}
    assert not (set(BASELINE_FEATURES) & banned), \
        "baseline can see the answer, so its residual would be meaningless"


# -------------------------------------------------------------- anomaly ---

def test_anomaly_threshold_comes_from_validation(obs_frame, rain_frame):
    X = _feature_frame(obs_frame, rain_frame)
    m = AnomalyModel().fit(X.iloc[:100])
    thr = m.calibrate(X.iloc[100:140], target_rate=0.05)
    assert np.isfinite(thr)
    assert "validation" in m.threshold_source_


def test_anomaly_records_when_it_fell_back_to_training(obs_frame, rain_frame):
    X = _feature_frame(obs_frame, rain_frame)
    m = AnomalyModel().fit(X.iloc[:100])
    m.calibrate(X.iloc[:5], target_rate=0.05)
    assert "training quantile" in m.threshold_source_


def test_anomaly_flag_rate_is_not_the_contamination(obs_frame, rain_frame):
    """Flag rate must follow the data, not a fixed constructor argument."""
    X = _feature_frame(obs_frame, rain_frame)
    m = AnomalyModel().fit(X.iloc[:100])
    m.calibrate(X.iloc[100:140], target_rate=0.20)
    rate = m.flag(X.iloc[100:140]).mean()
    assert rate > 0.05, "threshold did not respond to the requested rate"


# ----------------------------------------------------------- versioning ---

def test_bundle_rejects_a_changed_feature_set():
    b = ModelBundle("P05", "2.0", "2.0", ["a", "b"], features_fingerprint(["a", "b"]),
                    "test", {}, "2017-01-01", "2023-12-31")
    b.check_compatible(["a", "b"])
    with pytest.raises(ModelIncompatible, match="Retrain"):
        b.check_compatible(["a", "b", "c"])


def test_bundle_metadata_is_complete():
    b = ModelBundle("P05", "2.0", "2.0", list(FEATURE_COLUMNS),
                    features_fingerprint(FEATURE_COLUMNS), "test", {},
                    "2017-01-01", "2023-12-31")
    md = b.metadata()
    for k in ("model_version", "feature_version", "features", "training_start",
              "training_end", "created_at", "algorithm", "dataset_version"):
        assert k in md
    assert "estimators" not in md, "fitted objects must not leak into metadata"


def test_fingerprint_changes_with_feature_order():
    assert features_fingerprint(["a", "b"]) != features_fingerprint(["b", "a"])

"""Model contract tests: splits, fitting, versioning, compatibility."""
import os

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


@pytest.mark.skipif(not os.path.exists("data/observations/observations.csv"),
                    reason="no observations collected yet")
def test_severity_bands_form_a_pyramid():
    """Each tier must be rarer than the one below it, in every period.

    The thresholds were quantiles of the fitted model's residuals against its
    own training rows. A boosted tree fits those closely, so the ladder sat far
    too low -- 10.9% of readings at P05 cleared a bar meant for 0.5% -- and the
    top compressed until HIGH was 0.0005 wide and almost everything reaching it
    went straight to CRITICAL. 158 CRITICAL against 81 HIGH.
    """
    import collections
    import numpy as np
    import pandas as pd
    from pipeline.config import STATIONS, TRAIN_END, VALIDATION_END
    from pipeline.export.dashboard import station_frame
    from pipeline.features.builder import FEATURE_COLUMNS
    from pipeline.models.versioning import load_bundle
    from pipeline.satellite.observations import load_observations

    obs_all = load_observations()
    periods = {"train": (None, TRAIN_END), "validation": (TRAIN_END, VALIDATION_END),
               "test": (VALIDATION_END, None)}
    rates = {}
    for name, (lo, hi) in periods.items():
        tot, n = collections.Counter(), 0
        for st in STATIONS:
            obs, X = station_frame(st, obs_all)
            try:
                bl = load_bundle(st.id, features=FEATURE_COLUMNS).estimators["baseline"]
            except Exception:
                continue
            r = obs["ndti"].to_numpy(float) - bl.expected_for(X, obs["date"])
            m = np.isfinite(r)
            if lo:
                m &= (obs["date"] > pd.Timestamp(lo)).to_numpy()
            if hi:
                m &= (obs["date"] <= pd.Timestamp(hi)).to_numpy()
            r, n = r[m], n + int(m.sum())
            for k, t in zip("WEHC", [float(v) for v in bl.residual_thresholds_]):
                tot[k] += int((r >= t).sum())
        if not n:
            continue
        b = _bands_from(tot)
        assert b["WATCH"] >= b["ELEVATED"] >= b["HIGH"] >= b["CRITICAL"], \
            f"{name} severity is not a pyramid: {b}"
        rates[name] = sum(b.values()) / n

    # and the rate must not depend on whether the model had seen the period
    if {"train", "test"} <= set(rates):
        assert abs(rates["train"] - rates["test"]) < 0.10, (
            f"alert rate differs by period (train {rates['train']:.1%}, test "
            f"{rates['test']:.1%}); the model is recalling its training rows "
            f"rather than judging them")


def _bands_from(counter):
    return {"WATCH": counter["W"] - counter["E"],
            "ELEVATED": counter["E"] - counter["H"],
            "HIGH": counter["H"] - counter["C"],
            "CRITICAL": counter["C"]}

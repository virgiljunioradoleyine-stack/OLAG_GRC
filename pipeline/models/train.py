"""
Training orchestration: build features, split chronologically, fit, evaluate.

The training period boundary is enforced in one place. Everything fitted --
the baseline regressor, the anomaly detector, its scaler and its imputer -- sees
only training rows. Validation chooses thresholds. Test is untouched until the
final evaluation and is never used to select anything.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..config import BY_ID, FEATURE_VERSION, STATIONS, CONTROL_ID, upstream_neighbour
from ..features.builder import FEATURE_COLUMNS, build_features
from ..groundtruth.store import load_ground_truth, match_to_observations
from ..rainfall.client import load_rainfall
from ..satellite.observations import load_observations
from .anomaly import ANOMALY_FEATURES, AnomalyModel
from .baseline import BASELINE_FEATURES, ExpectedConditionModel
from .splits import DEFAULT_SPLIT, chronological_split, split_summary
from .versioning import ModelBundle, features_fingerprint, save_bundle

MODEL_VERSION = "2.0"


def station_frame(station, obs_all=None):
    """Observations + causal features for one station."""
    obs_all = load_observations() if obs_all is None else obs_all
    obs = obs_all[obs_all["station_id"] == station.id].copy()
    if obs.empty:
        return obs, pd.DataFrame(columns=FEATURE_COLUMNS)

    up = upstream_neighbour(station)
    up_df = obs_all[obs_all["station_id"] == up.id] if up else None
    ctl_df = obs_all[obs_all["station_id"] == CONTROL_ID]
    if station.id == CONTROL_ID:
        ctl_df = None
    rain = load_rainfall(station.id)

    X = build_features(obs, up_df, ctl_df, rain)
    return obs.reset_index(drop=True), X


def train_station(station, obs_all=None, spec=DEFAULT_SPLIT, verbose=True):
    """Fit both models for one station and return a versioned bundle."""
    obs, X = station_frame(station, obs_all)
    if obs.empty:
        if verbose:
            print(f"  {station.id}: no observations, skipping")
        return None

    # Reject unusable observations before they can influence anything.
    keep = obs["quality"].isin(["GOOD", "ACCEPTABLE", "LOW_QUALITY"]).to_numpy()
    obs, X = obs[keep].reset_index(drop=True), X[keep].reset_index(drop=True)

    tr, va, te = chronological_split(obs, spec)
    summary = split_summary(obs, spec)
    y = obs["ndti"].to_numpy(dtype=float)

    if tr.sum() < 40:
        if verbose:
            print(f"  {station.id}: only {int(tr.sum())} training rows, skipping")
        return None

    # weight by observation quality so a 20-pixel reading cannot dominate
    w = obs["quality_score"].to_numpy(dtype=float)
    w = np.where(np.isfinite(w), w, 0.5)

    baseline, base_val, base_test = None, {}, {}
    try:
        baseline = ExpectedConditionModel().fit(X[tr], y[tr], sample_weight=w[tr])
        base_val = baseline.evaluate(X[va], y[va]) if va.sum() >= 3 else {"n": int(va.sum())}
        base_test = baseline.evaluate(X[te], y[te]) if te.sum() >= 3 else {"n": int(te.sum())}
    except ValueError as ex:
        if verbose:
            print(f"  {station.id}: baseline not fitted — {ex}")

    anomaly = AnomalyModel().fit(X[tr])
    threshold = anomaly.calibrate(X[va] if va.sum() else None, target_rate=0.05)

    val_scores = anomaly.score(X[va]) if va.sum() else np.array([])
    test_scores = anomaly.score(X[te]) if te.sum() else np.array([])
    anom_metrics = {
        "threshold": round(float(threshold), 6),
        "threshold_source": anomaly.threshold_source_,
        "validation_flag_rate": round(float((val_scores < threshold).mean()), 4) if val_scores.size else None,
        "test_flag_rate": round(float((test_scores < threshold).mean()), 4) if test_scores.size else None,
    }

    # supervised calibration is only possible with real measurements
    gt = load_ground_truth()
    matched = match_to_observations(gt, obs, station.id) if not gt.empty else pd.DataFrame()
    supervised = {
        "available": bool(len(matched)),
        "matched_samples": int(len(matched)),
        "note": ("no in-situ measurements exist for this station; the system "
                 "reports an anomaly indicator, not calibrated turbidity"),
    }

    d = pd.to_datetime(obs["date"])
    bundle = ModelBundle(
        station_id=station.id,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        features=list(FEATURE_COLUMNS),
        feature_fingerprint=features_fingerprint(FEATURE_COLUMNS),
        algorithm="ExpectedCondition(HistGradientBoosting) + IsolationForest",
        hyperparameters={
            "baseline": baseline.params if baseline else None,
            "anomaly": {"n_estimators": anomaly.n_estimators,
                        "fit_contamination": 0.02,
                        "random_state": anomaly.random_state},
        },
        training_start=str(d[tr].min().date()),
        training_end=str(d[tr].max().date()),
        validation_start=str(d[va].min().date()) if va.sum() else "",
        validation_end=str(d[va].max().date()) if va.sum() else "",
        test_start=str(d[te].min().date()) if te.sum() else "",
        test_end=str(d[te].max().date()) if te.sum() else "",
        training_rows=int(tr.sum()),
        validation_rows=int(va.sum()),
        test_rows=int(te.sum()),
        dataset_version=datetime.now(timezone.utc).strftime("%Y%m%d"),
        validation_metrics={"baseline": base_val, "anomaly": anom_metrics,
                            "split": summary},
        test_metrics={"baseline": base_test},
        thresholds={"anomaly_score": round(float(threshold), 6)},
        estimators={"baseline": baseline, "anomaly": anomaly},
    )
    save_bundle(bundle)

    if verbose:
        mae = base_val.get("mae")
        skill = base_val.get("skill_vs_naive")
        print(f"  {station.id}: train={int(tr.sum())} val={int(va.sum())} "
              f"test={int(te.sum())}  baseline MAE={mae}  skill={skill}  "
              f"anomaly thr={threshold:.4f}")
    return bundle


def train_all(spec=DEFAULT_SPLIT, verbose=True):
    obs_all = load_observations()
    if obs_all.empty:
        print("no observations found — run the satellite collection first")
        return []
    bundles = []
    for s in STATIONS:
        b = train_station(s, obs_all, spec, verbose)
        if b:
            bundles.append(b)
    return bundles


def main():
    print("training models\n")
    bundles = train_all()
    print(f"\ntrained {len(bundles)} station models")
    return 0 if bundles else 1


if __name__ == "__main__":
    raise SystemExit(main())

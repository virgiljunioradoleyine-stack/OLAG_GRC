"""
Model A — unsupervised anomaly detection.

Kept from the original design because it earns its place: nobody has labelled
galamsey events on the Pra, so a supervised detector is not available to us.

Two changes from the audited version, both material:

  1. `contamination` no longer decides how many alerts exist. It is fitted at a
     fixed low value purely to make the estimator well-posed, and the operating
     threshold is then chosen from the VALIDATION period's score distribution.
     Previously "13 anomalies in 260 readings" was arithmetic -- 5% of 260 --
     dressed up as a finding.
  2. The scaler is fitted on the training period only, never the full series.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Features the detector sees. Excludes raw quality counters, which describe how
# well we measured rather than what the river did -- an unusual pixel count is
# an unusual *observation*, not an unusual river.
ANOMALY_FEATURES = [
    "ndti", "red", "ndwi", "mndwi", "red_green_ratio",
    "ndti_delta", "ndti_change_3d", "ndti_change_7d",
    "ndti_anom_30d", "red_anom_30d", "seasonal_anomaly",
    "month_sin", "month_cos",
    "rain_7d", "rain_30d", "rain_7d_anom",
    "upstream_diff", "control_diff",
]

FIT_CONTAMINATION = 0.02   # keeps the estimator well-posed; NOT the alert rate


class AnomalyModel:
    def __init__(self, n_estimators=300, random_state=42, features=None):
        self.features = list(features or ANOMALY_FEATURES)
        self.random_state = random_state
        self.n_estimators = n_estimators
        self.pipeline = None
        self.train_scores_ = None
        self.threshold_ = None
        self.threshold_source_ = None

    def _matrix(self, X):
        missing = [c for c in self.features if c not in X.columns]
        if missing:
            raise KeyError(f"anomaly features missing from frame: {missing}")
        return X[self.features].to_numpy(dtype=float)

    def fit(self, X_train):
        self.pipeline = Pipeline([
            # keep_empty_features keeps the column count stable between fit and
            # transform. Without it SimpleImputer silently DROPS an all-NaN
            # column, so a model fitted while rainfall was unavailable would
            # expect a different width once rainfall returned.
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
            ("forest", IsolationForest(
                n_estimators=self.n_estimators,
                contamination=FIT_CONTAMINATION,
                random_state=self.random_state,
                n_jobs=-1,
            )),
        ])
        M = self._matrix(X_train)
        if len(M) < 40:
            raise ValueError(f"anomaly model needs >= 40 training rows, got {len(M)}")
        self.pipeline.fit(M)
        self.train_scores_ = self.pipeline.named_steps["forest"].score_samples(
            self.pipeline.named_steps["scale"].transform(
                self.pipeline.named_steps["impute"].transform(M)))
        return self

    def score(self, X):
        """Lower = more anomalous (sklearn's score_samples convention)."""
        if self.pipeline is None:
            raise RuntimeError("AnomalyModel is not fitted")
        M = self._matrix(X)
        f = self.pipeline.named_steps
        return f["forest"].score_samples(
            f["scale"].transform(f["impute"].transform(M)))

    def calibrate(self, X_val, target_rate=0.05):
        """Choose the operating threshold from held-out data.

        The threshold is the `target_rate` quantile of validation scores, so it
        reflects how the model behaves on data it did not see. If validation is
        too small to be meaningful we fall back to the training distribution and
        record that we did, rather than silently pretending otherwise.
        """
        if X_val is not None and len(X_val) >= 30:
            scores = self.score(X_val)
            self.threshold_source_ = f"validation quantile ({len(scores)} rows)"
        else:
            scores = self.train_scores_
            n = 0 if X_val is None else len(X_val)
            self.threshold_source_ = (
                f"training quantile — validation had only {n} rows, "
                f"too few to calibrate on")
        self.threshold_ = float(np.quantile(scores, target_rate))
        return self.threshold_

    def flag(self, X):
        """True where the score falls below the calibrated threshold."""
        if self.threshold_ is None:
            raise RuntimeError("AnomalyModel is not calibrated")
        return self.score(X) < self.threshold_

    def percentile_of(self, score):
        """Where a score sits in the training distribution, 0-100."""
        if self.train_scores_ is None or not len(self.train_scores_):
            return float("nan")
        return float((self.train_scores_ < score).mean() * 100.0)

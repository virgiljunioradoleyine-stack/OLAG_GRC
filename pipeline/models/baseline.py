"""
Model B — the expected-condition baseline.

Answers: given the season, the rainfall, and what upstream is doing, what
turbidity index would we reasonably expect here today?

This is the piece the original system lacked. An Isolation Forest alone says
"this row is unusual" without saying what normal would have been, so it cannot
tell you *how far* off things are, and it cannot separate "unusual because it
rained hard" from "unusual for no visible reason". Fitting an explicit
expectation gives us a residual, and the residual is what the alert engine
reasons about.

HistGradientBoostingRegressor is the right size of hammer: it handles NaNs
natively (our features are gappy by nature -- cloud decides when we observe),
needs no scaling, is fast enough for CI, and is far easier to defend to a
reviewer than a neural network fitted to a few hundred rows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Features the baseline is allowed to see. Deliberately EXCLUDES the target
# itself and any same-day transform of it (ndti_delta, seasonal_anomaly, ...),
# which would make the problem trivial and the residual meaningless.
BASELINE_FEATURES = [
    "month_sin", "month_cos", "seasonal_baseline",
    "ndti_mean_7d", "ndti_mean_14d", "ndti_mean_30d",
    "rain_1d", "rain_3d", "rain_7d", "rain_14d", "rain_30d",
    "rain_7d_anom", "rain_30d_anom",
    "upstream_ndti", "upstream_delta", "upstream_lag_days",
    "control_ndti", "control_delta",
    "water_pixel_count", "cloud_fraction", "quality_score",
]

TARGET = "ndti"


class ExpectedConditionModel:
    """Predicts the expected index value; the residual is what matters."""

    def __init__(self, random_state=42, **kw):
        self.random_state = random_state
        self.params = dict(
            max_iter=300, learning_rate=0.06, max_depth=4,
            min_samples_leaf=10, l2_regularization=1.0,
            early_stopping=False, random_state=random_state,
        )
        self.params.update(kw)
        self.model = None
        self.features = list(BASELINE_FEATURES)
        self.fitted_features_ = None   # the subset actually usable at fit time
        self.dropped_features_ = []
        self.residual_std_ = None
        self.residual_thresholds_ = None   # empirical watch/elevated/high/critical
        self.oof_expected_ = {}            # date -> expectation before training on it

    # --- helpers ----------------------------------------------------------
    def _matrix(self, X, cols=None):
        cols = cols or self.fitted_features_ or self.features
        missing = [c for c in cols if c not in X.columns]
        if missing:
            raise KeyError(f"baseline features missing from frame: {missing}")
        return X[cols].to_numpy(dtype=float)

    @staticmethod
    def _usable(y, sample_weight=None):
        m = np.isfinite(y)
        if sample_weight is not None:
            m &= np.isfinite(sample_weight)
        return m

    # --- API --------------------------------------------------------------
    def fit(self, X, y, sample_weight=None, dates=None):
        y = np.asarray(y, dtype=float)
        m = self._usable(y, sample_weight)
        if m.sum() < 30:
            raise ValueError(
                f"expected-condition model needs >= 30 usable training rows, got {int(m.sum())}")

        # Drop features with no observed value in the training window. An
        # all-NaN column carries no information, and the gradient booster
        # cannot bin one -- it fails with an opaque "window shape cannot be
        # larger than input array shape". This is not hypothetical: if the
        # rainfall API is unavailable, every rainfall feature arrives empty and
        # the whole model would refuse to fit. Dropping them lets the model
        # degrade to what it can actually see, and records what it lost.
        present = [c for c in self.features
                   if c in X.columns and np.isfinite(
                       pd.to_numeric(X[c], errors="coerce").to_numpy(dtype=float)[m]).any()]
        self.dropped_features_ = [c for c in self.features if c not in present]
        if len(present) < 3:
            raise ValueError(
                f"only {len(present)} usable baseline features; cannot fit")
        self.fitted_features_ = present

        M = self._matrix(X, present)
        self.model = HistGradientBoostingRegressor(**self.params)
        self.model.fit(M[m], y[m],
                       sample_weight=None if sample_weight is None else np.asarray(sample_weight)[m])
        # Spread and severity thresholds come from OUT-OF-FOLD residuals, never
        # from the residuals of this fitted model against its own training rows.
        #
        # A boosted tree fits its training data closely, so in-sample residuals
        # are far tighter than the errors the model will actually make. Taking
        # quantiles of them set the whole ladder far too low -- 10.9% of
        # observations at P05 cleared a bar meant to be exceeded 0.5% of the
        # time -- and, worse, compressed the top: P05's 96th and 99.5th
        # percentiles came out at 0.00809 and 0.00862, so the HIGH band was
        # 0.0005 wide and almost everything that reached HIGH went straight
        # past it to CRITICAL. That is what kept the severity pyramid inverted.
        #
        # Rolling-origin folds give honest forward-looking errors from the same
        # training window: each fold fits on the past and predicts the next
        # block, so no threshold is set from a prediction the model had already
        # seen the answer to. Validation stays free for choosing the anomaly
        # threshold, and the test period is still never touched.
        resid, oof = self._out_of_fold_residuals(
            M[m], y[m],
            None if sample_weight is None else np.asarray(sample_weight)[m])
        self._store_oof(dates, m, oof)

        # robust spread: MAD scaled to a normal-equivalent sigma
        self.residual_std_ = float(1.4826 * np.median(np.abs(resid - np.median(resid))))
        if not np.isfinite(self.residual_std_) or self.residual_std_ <= 0:
            self.residual_std_ = float(np.std(resid)) or 1e-6

        # These residuals are strongly non-normal, so a MAD-scaled sigma cannot
        # be read as implying Gaussian rarity -- doing so also produced an
        # inverted pyramid. Quantiles of the actual distribution are
        # distribution-free and give each tier the frequency we intend.
        pos = resid[resid > 0]
        if pos.size >= 20:
            q = np.quantile(pos, [0.60, 0.85, 0.96, 0.995])
        else:
            q = np.array([1, 2, 3, 4], dtype=float) * self.residual_std_
        self.residual_thresholds_ = [float(v) for v in q]   # watch/elev/high/crit
        return self

    def _out_of_fold_residuals(self, M, y, sample_weight=None, n_splits=4):
        """Forward-chaining residuals over the training window.

        Falls back to in-sample residuals only when there is too little history
        to split, which is the one case where they are the best available.
        """
        from sklearn.model_selection import TimeSeriesSplit

        n = len(y)
        if n < 60:
            return y - self.model.predict(M), {}

        out, preds = [], {}
        for tr, te in TimeSeriesSplit(n_splits=n_splits).split(M):
            # An early fold is short, and a feature can be constant within it.
            # HistGradientBoosting cannot bin a column with a single distinct
            # value -- it fails outright -- so each fold keeps only the columns
            # that actually vary in its own training rows. This is the same
            # hazard as the all-NaN columns dropped at full-fit time, just
            # reached by a smaller sample.
            keep = [j for j in range(M.shape[1])
                    if np.unique(M[tr, j][np.isfinite(M[tr, j])]).size >= 2]
            if not keep:
                continue
            fold = HistGradientBoostingRegressor(**self.params)
            fold.fit(M[np.ix_(tr, keep)], y[tr],
                     None if sample_weight is None else sample_weight[tr])
            p = fold.predict(M[np.ix_(te, keep)])
            out.append(y[te] - p)
            for i, v in zip(te, p):
                preds[int(i)] = float(v)
        if not out:
            return y - self.model.predict(M), {}
        resid = np.concatenate(out)
        if resid.size < 20:
            return y - self.model.predict(M), {}
        return resid, preds

    def _store_oof(self, dates, mask, oof):
        """Remember what each training row looked like BEFORE it was trained on.

        The final model has seen every training row, so its residuals there are
        memory, not judgement: on this record the alert rate over the training
        period came out at 0.2% against 17.6% on unseen data. Plotting that as
        history would show nine calm years and then a sudden onset of alerts in
        2024 -- an artifact of when training stopped, presented as if it were
        something the river did. Keeping the fold predictions lets the dashboard
        show, for each historical date, what the system would have said at the
        time.
        """
        self.oof_expected_ = {}
        if dates is None or not oof:
            return
        d = pd.to_datetime(pd.Series(list(dates))).dt.strftime("%Y-%m-%d").to_numpy()
        kept = np.nonzero(np.asarray(mask))[0]      # row index into the full frame
        for pos, value in oof.items():
            if pos < len(kept):
                self.oof_expected_[str(d[kept[pos]])] = value

    def predict(self, X):
        if self.model is None:
            raise RuntimeError("ExpectedConditionModel is not fitted")
        return self.model.predict(self._matrix(X))

    def expected_for(self, X, dates=None):
        """Expectation for display: out-of-fold where the row was trained on.

        `predict` stays the pure model. This is what the dashboard and the alert
        engine should use over a series that spans the training period, so a
        historical reading is judged against what was expected of it at the
        time rather than against a model that already knew the answer.
        """
        out = self.predict(X)
        oof = getattr(self, "oof_expected_", None)
        if not oof or dates is None:
            return out
        keys = pd.to_datetime(pd.Series(list(dates))).dt.strftime("%Y-%m-%d")
        for i, k in enumerate(keys):
            if k in oof:
                out[i] = oof[k]
        return out

    def residuals(self, X, y):
        return np.asarray(y, dtype=float) - self.predict(X)

    def z_scores(self, X, y):
        """Residual expressed in robust standard deviations."""
        return self.residuals(X, y) / (self.residual_std_ or 1e-6)

    def evaluate(self, X, y):
        y = np.asarray(y, dtype=float)
        m = np.isfinite(y)
        if m.sum() < 3:
            return {"n": int(m.sum())}
        pred = self.predict(X)[m]
        yt = y[m]
        # naive reference: predict the station's own rolling 30-day mean
        naive = X["ndti_mean_30d"].to_numpy(dtype=float)[m]
        nm = np.isfinite(naive)
        out = {
            "n": int(m.sum()),
            "mae": round(float(mean_absolute_error(yt, pred)), 5),
            "rmse": round(float(np.sqrt(mean_squared_error(yt, pred))), 5),
            "r2": round(float(r2_score(yt, pred)), 4) if m.sum() > 2 else None,
            "residual_std": round(float(self.residual_std_ or 0), 5),
        }
        if nm.sum() > 2:
            out["naive_mae"] = round(float(mean_absolute_error(yt[nm], naive[nm])), 5)
            out["skill_vs_naive"] = round(
                1 - out["mae"] / out["naive_mae"], 4) if out["naive_mae"] else None
        return out

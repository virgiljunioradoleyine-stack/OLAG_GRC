"""Temporal-leakage tests. These are the tests that matter most."""
import numpy as np
import pandas as pd
import pytest

from pipeline.features.builder import FEATURE_COLUMNS, build_features


def test_future_data_cannot_change_past_features(obs_frame, rain_frame, dates):
    """Mutate everything after a cut date; no earlier feature may move."""
    obs, up, ctl = obs_frame(1), obs_frame(2, "P04"), obs_frame(3, "P01")
    X = build_features(obs, up, ctl, rain_frame)

    cut = 80
    obs2, up2, ctl2 = obs.copy(), up.copy(), ctl.copy()
    rain2 = rain_frame.copy()
    obs2.loc[cut:, "ndti"] += 9.0
    obs2.loc[cut:, "red"] += 9.0
    up2.loc[cut:, "ndti"] += 9.0
    ctl2.loc[cut:, "ndti"] += 9.0
    rain2.loc[rain2["date"] > dates[cut], "precip_mm"] += 500.0
    X2 = build_features(obs2, up2, ctl2, rain2)

    leaked = []
    for c in FEATURE_COLUMNS:
        a = X[c].to_numpy(float)[:cut]
        b = X2[c].to_numpy(float)[:cut]
        both = np.isfinite(a) & np.isfinite(b)
        if both.any() and not np.allclose(a[both], b[both], atol=1e-9):
            leaked.append(c)
        if (np.isnan(a) != np.isnan(b)).any():
            leaked.append(f"{c}(nan-pattern)")
    assert not leaked, f"future data leaked into past features: {leaked}"


def test_upstream_lag_is_never_negative(obs_frame, rain_frame):
    X = build_features(obs_frame(1), obs_frame(2, "P04"), obs_frame(3, "P01"), rain_frame)
    lag = X["upstream_lag_days"].to_numpy(float)
    lag = lag[np.isfinite(lag)]
    assert (lag >= 0).all(), "upstream observation taken from the future"


def test_rolling_means_are_backward_looking(obs_frame, rain_frame):
    """A 30-day mean must equal the mean of prior-or-equal observations only."""
    obs = obs_frame(1)
    X = build_features(obs, None, None, rain_frame)
    days = obs["date"].values.astype("datetime64[D]").astype(int)
    v = obs["ndti"].to_numpy(float)
    for i in (30, 60, 120):
        m = (days <= days[i]) & (days > days[i] - 30)
        assert np.isclose(X["ndti_mean_30d"].iloc[i], v[m].mean(), atol=1e-9)


def test_seasonal_baseline_uses_prior_years_only(obs_frame, rain_frame):
    obs = obs_frame(1)
    X = build_features(obs, None, None, rain_frame)
    first_year = obs["date"].dt.year == obs["date"].dt.year.min()
    assert X.loc[first_year.to_numpy(), "seasonal_baseline"].isna().all(), \
        "first year has no prior years, so it must have no seasonal baseline"


def test_scaler_not_fitted_on_full_series():
    """The anomaly pipeline must be fitted only on the rows it is given."""
    from pipeline.models.anomaly import AnomalyModel, ANOMALY_FEATURES
    r = np.random.default_rng(0)
    train = pd.DataFrame({c: r.normal(0, 1, 100) for c in ANOMALY_FEATURES})
    future = pd.DataFrame({c: r.normal(50, 1, 50) for c in ANOMALY_FEATURES})
    m = AnomalyModel().fit(train)
    means = m.pipeline.named_steps["scale"].mean_
    assert np.abs(means).max() < 5, "scaler saw data far outside the training set"
    assert m.score(future).mean() < m.score(train).mean(), \
        "wildly out-of-range rows should score as more anomalous"

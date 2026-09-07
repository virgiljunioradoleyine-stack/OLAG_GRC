import numpy as np
import pandas as pd

from pipeline.features.builder import FEATURE_COLUMNS, build_features


def test_all_declared_features_are_produced(obs_frame, rain_frame):
    X = build_features(obs_frame(1), obs_frame(2, "P04"), obs_frame(3, "P01"), rain_frame)
    assert list(X.columns) == FEATURE_COLUMNS
    assert len(X) == len(obs_frame(1))


def test_ndti_matches_the_source_column(obs_frame, rain_frame):
    obs = obs_frame(1)
    X = build_features(obs, None, None, rain_frame)
    assert np.allclose(X["ndti"], obs["ndti"])


def test_cyclical_month_encoding_wraps(obs_frame, rain_frame):
    """December and January must be near neighbours, not 11 units apart."""
    obs = obs_frame(1)
    X = build_features(obs, None, None, rain_frame)
    m = obs["date"].dt.month.to_numpy()
    dec = (m == 12)
    jan = (m == 1)
    if dec.any() and jan.any():
        d = np.hypot(X["month_sin"][dec].mean() - X["month_sin"][jan].mean(),
                     X["month_cos"][dec].mean() - X["month_cos"][jan].mean())
        d_far = np.hypot(X["month_sin"][dec].mean() - X["month_sin"][m == 6].mean(),
                         X["month_cos"][dec].mean() - X["month_cos"][m == 6].mean())
        assert d < d_far, "cyclical encoding did not wrap December to January"


def test_rainfall_windows_are_cumulative(obs_frame, rain_frame):
    X = build_features(obs_frame(1), None, None, rain_frame)
    ok = X[["rain_1d", "rain_7d", "rain_30d"]].dropna()
    assert (ok["rain_7d"] >= ok["rain_1d"] - 1e-9).all()
    assert (ok["rain_30d"] >= ok["rain_7d"] - 1e-9).all()


def test_missing_rainfall_degrades_to_nan_not_zero(obs_frame):
    """No rainfall data must not silently look like 'it did not rain'."""
    X = build_features(obs_frame(1), None, None, None)
    assert X["rain_7d"].isna().all()


def test_upstream_diff_is_self_consistent(obs_frame, rain_frame):
    obs, up = obs_frame(1), obs_frame(2, "P04")
    X = build_features(obs, up, None, rain_frame)
    m = X["upstream_ndti"].notna()
    assert np.allclose(X.loc[m, "upstream_diff"],
                       X.loc[m, "ndti"] - X.loc[m, "upstream_ndti"])

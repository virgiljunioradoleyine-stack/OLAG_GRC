"""
Feature construction — strictly causal.

Every feature here answers the question "what could we have known at the moment
this observation was taken?". That constraint is not stylistic: the audit found
the previous implementation matching each downstream reading to the *nearest*
upstream reading, which could be up to ten days in the future. A model trained
that way looks good in backtest and cannot work in production, because at
prediction time the future half of its inputs does not exist.

Three rules enforced throughout, and tested in tests/test_leakage.py:

  1. Rolling windows cover (t - w, t]. Never t + anything.
  2. Upstream matching only accepts observations at or before t.
  3. Rainfall windows end on t.

Seasonality is encoded cyclically. A raw month integer tells a tree that
December (12) and January (1) are eleven units apart, which is the opposite of
the truth for a river with an annual cycle.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import CONTROL_MATCH_MAX_DAYS, FEATURE_VERSION  # noqa: F401
from ..rainfall.client import WINDOWS as RAIN_WINDOWS, rainfall_windows

# Rolling windows in days for the station's own history.
ROLL_WINDOWS = (7, 14, 30)
# Change windows in days.
DIFF_WINDOWS = (3, 7)

FEATURE_COLUMNS = [
    # --- spectral (what the sensor saw) ---
    "ndti", "red", "green", "nir", "swir16", "ndwi", "mndwi", "red_green_ratio",
    # --- temporal (how it changed) ---
    "ndti_delta", "ndti_change_3d", "ndti_change_7d",
    "ndti_mean_7d", "ndti_mean_14d", "ndti_mean_30d",
    "ndti_anom_30d", "red_delta", "red_mean_30d", "red_anom_30d",
    # --- seasonality (what is normal for this time of year) ---
    "month_sin", "month_cos", "seasonal_baseline", "seasonal_anomaly",
    # --- rainfall (the innocent explanation) ---
    "rain_1d", "rain_3d", "rain_7d", "rain_14d", "rain_30d",
    "rain_7d_anom", "rain_30d_anom",
    # --- spatial (what upstream was doing) ---
    "upstream_ndti", "upstream_delta", "upstream_lag_days",
    "upstream_diff", "control_ndti", "control_delta", "control_diff",
    # --- quality (how much to trust this row) ---
    "water_pixel_count", "cloud_fraction", "ndti_std", "quality_score",
]


def _rolling_mean(days, values, window):
    """Mean over (t - window, t], inclusive of t. Strictly backward-looking."""
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        m = (days <= days[i]) & (days > days[i] - window)
        vals = values[m]
        vals = vals[np.isfinite(vals)]
        if vals.size:
            out[i] = vals.mean()
    return out


def _change_over(days, values, window):
    """value(t) - value(most recent observation at or before t - window)."""
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        prior = np.nonzero(days <= days[i] - window)[0]
        if prior.size and np.isfinite(values[i]) and np.isfinite(values[prior[-1]]):
            out[i] = values[i] - values[prior[-1]]
    return out


def _seasonal_baseline(dates, values, half_window=15):
    """Expected value for this day-of-year, learned from PRIOR YEARS ONLY.

    Excluding the current year is what stops a station's own anomalous season
    from being absorbed into its own baseline. Excluding later years is what
    stops the future leaking in.
    """
    doy = dates.dt.dayofyear.to_numpy()
    year = dates.dt.year.to_numpy()
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        # circular day-of-year distance, so 1 Jan is close to 31 Dec
        d = np.abs(doy - doy[i])
        d = np.minimum(d, 365 - d)
        m = (d <= half_window) & (year < year[i]) & np.isfinite(values)
        if m.sum() >= 3:
            out[i] = values[m].mean()
    return out


def _match_upstream(dates, up_df, column="ndti", max_days=CONTROL_MATCH_MAX_DAYS):
    """Most recent upstream observation at or BEFORE each date.

    This is the leakage fix. The previous implementation took the nearest
    observation in either direction, so a downstream reading could be explained
    by an upstream reading that had not happened yet.
    """
    n = len(dates)
    value = np.full(n, np.nan)
    delta = np.full(n, np.nan)
    lag = np.full(n, np.nan)
    if up_df is None or up_df.empty or column not in up_df.columns:
        return value, delta, lag

    up = up_df.sort_values("date")
    updays = up["date"].values.astype("datetime64[D]").astype(int)
    upvals = pd.to_numeric(up[column], errors="coerce").to_numpy(dtype=float)
    updelta = np.concatenate([[np.nan], np.diff(upvals)])
    days = pd.to_datetime(pd.Series(list(dates))).values.astype("datetime64[D]").astype(int)

    for i, day in enumerate(days):
        prior = np.nonzero((updays <= day) & np.isfinite(upvals))[0]
        if not prior.size:
            continue
        j = prior[-1]
        if day - updays[j] <= max_days:
            value[i] = upvals[j]
            delta[i] = updelta[j]
            lag[i] = day - updays[j]
    return value, delta, lag


def build_features(obs_df, upstream_df=None, control_df=None, rain_df=None):
    """Build the causal feature table for one station's observations.

    `obs_df` must be sorted by date and contain a single station.
    """
    df = obs_df.sort_values("date").reset_index(drop=True)
    f = pd.DataFrame(index=df.index)
    days = df["date"].values.astype("datetime64[D]").astype(int)

    def col(name):
        return pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=float) \
            if name in df.columns else np.full(len(df), np.nan)

    ndti, red = col("ndti"), col("red")

    # --- spectral -------------------------------------------------------
    for c in ("ndti", "red", "green", "nir", "swir16", "ndwi", "mndwi",
              "red_green_ratio"):
        f[c] = col(c)

    # --- temporal -------------------------------------------------------
    f["ndti_delta"] = np.concatenate([[np.nan], np.diff(ndti)])
    for w in DIFF_WINDOWS:
        f[f"ndti_change_{w}d"] = _change_over(days, ndti, w)
    for w in ROLL_WINDOWS:
        f[f"ndti_mean_{w}d"] = _rolling_mean(days, ndti, w)
    f["ndti_anom_30d"] = ndti - f["ndti_mean_30d"].to_numpy()
    f["red_delta"] = np.concatenate([[np.nan], np.diff(red)])
    f["red_mean_30d"] = _rolling_mean(days, red, 30)
    f["red_anom_30d"] = red - f["red_mean_30d"].to_numpy()

    # --- seasonality ----------------------------------------------------
    month = df["date"].dt.month.to_numpy()
    f["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    f["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    base = _seasonal_baseline(df["date"], ndti)
    f["seasonal_baseline"] = base
    f["seasonal_anomaly"] = ndti - base

    # --- rainfall -------------------------------------------------------
    rw = rainfall_windows(rain_df, df["date"], windows=RAIN_WINDOWS)
    for w in RAIN_WINDOWS:
        f[f"rain_{w}d"] = rw[f"rain_{w}d"].to_numpy()
    f["rain_7d_anom"] = rw["rain_7d_anom"].to_numpy()
    f["rain_30d_anom"] = rw["rain_30d_anom"].to_numpy()

    # --- spatial --------------------------------------------------------
    up_v, up_d, up_lag = _match_upstream(df["date"], upstream_df, "ndti")
    f["upstream_ndti"] = up_v
    f["upstream_delta"] = up_d
    f["upstream_lag_days"] = up_lag
    f["upstream_diff"] = ndti - up_v

    c_v, c_d, _c_lag = _match_upstream(df["date"], control_df, "ndti")
    f["control_ndti"] = c_v
    f["control_delta"] = c_d
    f["control_diff"] = ndti - c_v

    # --- quality --------------------------------------------------------
    f["water_pixel_count"] = col("water_pixel_count")
    f["cloud_fraction"] = col("cloud_fraction")
    f["ndti_std"] = col("ndti_std")
    f["quality_score"] = col("quality_score")

    return f[FEATURE_COLUMNS]

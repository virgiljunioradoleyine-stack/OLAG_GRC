"""
Rainfall acquisition, caching and window features.

Caching matters: the historical record back to 2017 is fixed, so re-downloading
it on every scheduled run would be thousands of redundant requests against a
free public service. The cache is a CSV per station; only the gap between the
last cached day and today is ever fetched.
"""
from __future__ import annotations

import csv
import os
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from ..io.atomic import atomic_write
from .providers import RainfallUnavailable, fetch_daily

RAINFALL_DIR = "data/rainfall"
FIELDS = ["date", "precip_mm", "source"]

# Windows the alert engine reasons over, in days.
WINDOWS = (1, 3, 7, 14, 30)


def _path(station_id, directory=RAINFALL_DIR):
    return os.path.join(directory, f"{station_id}.csv")


def load_rainfall(station_id, directory=RAINFALL_DIR):
    """Cached daily rainfall for one station, or an empty frame."""
    p = _path(station_id, directory)
    if not os.path.exists(p):
        return pd.DataFrame(columns=FIELDS).astype({"precip_mm": float})
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    df["precip_mm"] = pd.to_numeric(df["precip_mm"], errors="coerce")
    return df.dropna(subset=["precip_mm"]).sort_values("date").reset_index(drop=True)


def _write(station_id, rows, directory=RAINFALL_DIR):
    os.makedirs(directory, exist_ok=True)
    with atomic_write(_path(station_id, directory)) as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return _path(station_id, directory)


def fetch_station_rainfall(station, start=None, end=None, directory=RAINFALL_DIR,
                           verbose=True):
    """Bring one station's rainfall cache up to date. Returns the full frame.

    Only the missing tail is downloaded. NASA POWER lags real time by a few
    days, so the most recent dates may legitimately be absent -- that is
    reported, not treated as an error.
    """
    existing = load_rainfall(station.id, directory)
    end = date.fromisoformat(end) if isinstance(end, str) else (end or date.today())
    start = date.fromisoformat(start) if isinstance(start, str) else start

    if not existing.empty:
        have_from = existing["date"].min().date()
        have_to = existing["date"].max().date()
        fetch_from = have_to + timedelta(days=1)
        if start and start < have_from:
            fetch_from = start          # backfill requested earlier history
        if fetch_from > end:
            if verbose:
                print(f"  {station.id}: rainfall cache current "
                      f"({len(existing)} days to {have_to})")
            return existing
    else:
        fetch_from = start or date(2017, 1, 1)

    if verbose:
        print(f"  {station.id}: fetching rainfall {fetch_from} .. {end}")
    values, source = fetch_daily(station.lat, station.lon, fetch_from, end)

    merged = {}
    for _, r in existing.iterrows():
        merged[r["date"].strftime("%Y-%m-%d")] = {
            "date": r["date"].strftime("%Y-%m-%d"),
            "precip_mm": float(r["precip_mm"]),
            "source": r.get("source", "unknown"),
        }
    for d, mm in values.items():
        merged[d] = {"date": d, "precip_mm": mm, "source": source}

    rows = [merged[k] for k in sorted(merged)]
    _write(station.id, rows, directory)
    if verbose:
        print(f"  {station.id}: {len(rows)} rainfall days cached "
              f"(+{len(rows) - len(existing)} new, source={source})")
    return load_rainfall(station.id, directory)


def rainfall_windows(rain_df, observation_dates, windows=WINDOWS):
    """Backward-looking rainfall totals ending on each observation date.

    STRICTLY backward-looking and inclusive of the observation day: window w
    covers (date - w, date]. Nothing after the observation date can enter, which
    is what keeps rainfall from leaking the future into a prediction.

    Also returns, per window, the anomaly against a day-of-year climatology
    built from OTHER years only -- so a wet year does not normalise itself away.
    """
    n = len(observation_dates)
    out = {f"rain_{w}d": np.full(n, np.nan) for w in windows}
    out.update({f"rain_{w}d_anom": np.full(n, np.nan) for w in windows})
    if rain_df is None or rain_df.empty:
        return pd.DataFrame(out, index=getattr(observation_dates, "index", None))

    rdays = rain_df["date"].values.astype("datetime64[D]").astype(int)
    rvals = rain_df["precip_mm"].to_numpy(dtype=float)
    ryear = rain_df["date"].dt.year.to_numpy()
    rdoy = rain_df["date"].dt.dayofyear.to_numpy()

    obs = pd.to_datetime(pd.Series(list(observation_dates)))
    odays = obs.values.astype("datetime64[D]").astype(int)
    oyear = obs.dt.year.to_numpy()
    odoy = obs.dt.dayofyear.to_numpy()

    for w in windows:
        totals = np.full(n, np.nan)
        anoms = np.full(n, np.nan)
        for i in range(n):
            m = (rdays <= odays[i]) & (rdays > odays[i] - w)
            if not m.any():
                continue
            totals[i] = float(rvals[m].sum())

            # climatology for the same day-of-year window, other years only
            doy_lo, doy_hi = odoy[i] - w + 1, odoy[i]
            same = ((rdoy >= doy_lo) & (rdoy <= doy_hi) & (ryear != oyear[i]))
            if same.sum() >= w:          # need at least ~1 comparable year
                per_year = (pd.DataFrame({"y": ryear[same], "v": rvals[same]})
                            .groupby("y")["v"].sum())
                if len(per_year) >= 2:
                    anoms[i] = float(totals[i] - per_year.mean())
        out[f"rain_{w}d"] = totals
        out[f"rain_{w}d_anom"] = anoms

    return pd.DataFrame(out, index=getattr(observation_dates, "index", None))


def main():
    """Update the rainfall cache for every configured station."""
    from ..config import STATIONS, HISTORY_START
    ok, failed = 0, []
    for s in STATIONS:
        try:
            fetch_station_rainfall(s, start=HISTORY_START)
            ok += 1
        except RainfallUnavailable as ex:
            print(f"  {s.id}: RAINFALL UNAVAILABLE -- {ex}")
            failed.append(s.id)
    print(f"\nrainfall: {ok}/{len(STATIONS)} stations updated"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed and ok == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

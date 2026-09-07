"""
Daily precipitation providers. All anonymous, no API key, no account.

Two independent providers are implemented so that one source going down does not
stop the pipeline. Both were verified reachable from GitHub Actions on
2026-09-07 -- see data/sources/probe_evidence.json.

  NASA POWER   (primary)  satellite + reanalysis, daily, global, from 1981.
                          https://power.larc.nasa.gov/docs/services/api/
  Open-Meteo   (fallback) ERA5 reanalysis archive, daily, global, from 1940.
                          https://open-meteo.com/en/docs/historical-weather-api

Rainfall matters here because turbidity rises after rain for entirely innocent
reasons. Without it the system cannot separate "the river is dirty because it
rained" from "the river is dirty and it did not rain", which is the whole basis
of the warning.
"""
from __future__ import annotations

import time
from datetime import date, datetime

import requests

TIMEOUT = 60
MAX_RETRIES = 4
BACKOFF = 2.0
UA = {"User-Agent": "PraRiverWatch/1.0 (open-source river monitoring; +https://github.com/virgiljunioradoleyine-stack/OLAG_GRC)"}

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# NASA POWER uses -999 for missing values
POWER_FILL = -999.0


class RainfallUnavailable(RuntimeError):
    """No provider could supply rainfall for the requested window."""


def _get(url, params):
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT, headers=UA)
            if r.status_code == 200:
                return r.json()
            # 429/5xx are worth retrying; 4xx generally are not
            if r.status_code < 500 and r.status_code != 429:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as ex:          # network error or the raise above
            last = ex
            if isinstance(ex, RuntimeError) and "HTTP 4" in str(ex):
                raise
        if attempt < MAX_RETRIES - 1:
            time.sleep(BACKOFF ** attempt)
    raise RainfallUnavailable(f"{url}: {last}")


def _as_date(d):
    return d if isinstance(d, date) else datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def nasa_power_daily(lat, lon, start, end):
    """{'YYYY-MM-DD': mm} of daily precipitation from NASA POWER."""
    s, e = _as_date(start), _as_date(end)
    data = _get(NASA_POWER_URL, {
        "parameters": "PRECTOTCORR",
        "community": "AG",
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "start": s.strftime("%Y%m%d"),
        "end": e.strftime("%Y%m%d"),
        "format": "JSON",
    })
    raw = (data.get("properties", {}).get("parameter", {}) or {}).get("PRECTOTCORR", {})
    out = {}
    for k, v in raw.items():
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        if val <= POWER_FILL + 1:        # missing sentinel
            continue
        out[f"{k[:4]}-{k[4:6]}-{k[6:8]}"] = round(val, 3)
    if not out:
        raise RainfallUnavailable("NASA POWER returned no usable values")
    return out


def open_meteo_daily(lat, lon, start, end):
    """{'YYYY-MM-DD': mm} of daily precipitation from the ERA5 archive."""
    s, e = _as_date(start), _as_date(end)
    data = _get(OPEN_METEO_URL, {
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "start_date": s.isoformat(),
        "end_date": e.isoformat(),
        "daily": "precipitation_sum",
        "timezone": "UTC",
    })
    daily = data.get("daily", {}) or {}
    times = daily.get("time", []) or []
    vals = daily.get("precipitation_sum", []) or []
    out = {t: round(float(v), 3) for t, v in zip(times, vals) if v is not None}
    if not out:
        raise RainfallUnavailable("Open-Meteo returned no usable values")
    return out


PROVIDERS = [
    ("nasa_power", nasa_power_daily),
    ("open_meteo", open_meteo_daily),
]


def fetch_daily(lat, lon, start, end):
    """Try each provider in order. Returns (values, provider_name).

    Raises RainfallUnavailable only when every provider fails, so a single
    outage degrades to the fallback rather than stopping the pipeline.
    """
    errors = []
    for name, fn in PROVIDERS:
        try:
            return fn(lat, lon, start, end), name
        except Exception as ex:
            errors.append(f"{name}: {ex}")
    raise RainfallUnavailable("; ".join(errors))

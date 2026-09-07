"""
Build the dashboard's data files.

The web app reads static JSON from web/public/data. That keeps the deployment to
GitHub + Vercel with no server to maintain, and makes every number the dashboard
shows traceable to a committed file.

Two rules this module enforces:

  1. Nothing is exported unless it came from the pipeline. There are no
     placeholder figures anywhere in the payload.
  2. Model metadata travels WITH the results, so the dashboard can state which
     model version produced a status and when it was trained. The audit found a
     dashboard confidently displaying metadata from a model that no longer
     matched the code; the freshness fields here exist to make that visible
     rather than invisible.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..alerting.engine import assess_series
from ..config import BY_ID, STATIONS, upstream_neighbour
from ..features.builder import FEATURE_COLUMNS
from ..groundtruth.store import load_ground_truth
from ..hydrology.network import load_network
from ..hydrology.overpass import load_river
from ..io.atomic import read_json, write_json
from ..models.train import station_frame
from ..models.versioning import ModelIncompatible, load_bundle
from ..rainfall.client import load_rainfall
from ..satellite.observations import load_observations

WEB_DATA_DIR = os.path.join("web", "public", "data")

INDICATOR_NAME = "Sediment Anomaly Index"
INDICATOR_SHORT = "SAI"
INDICATOR_NOTE = (
    "A satellite-derived index of surface-water sediment conditions, not a "
    "measured turbidity value. No in-situ measurements exist to calibrate it "
    "against, so it is deliberately reported as an index rather than in NTU."
)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _series_records(obs, X, assessments, rain):
    """One row per observation, carrying everything the charts need."""
    out = []
    rain_by_date = {}
    if rain is not None and not rain.empty:
        rain_by_date = {d.strftime("%Y-%m-%d"): float(v) for d, v
                        in zip(rain["date"], rain["precip_mm"])}
    for i in range(len(obs)):
        r = obs.iloc[i]
        a = assessments[i] if i < len(assessments) else None
        d = r["date"].strftime("%Y-%m-%d")
        rec = {
            "date": d,
            "indicator": round(float(r["ndti"]), 5),
            "quality": r.get("quality"),
            "water_pixels": int(r.get("water_pixel_count") or 0),
            "cloud_fraction": (round(float(r["cloud_fraction"]), 3)
                               if pd.notna(r.get("cloud_fraction")) else None),
        }
        for key, col in (("expected", None), ("rain_7d", "rain_7d"),
                         ("rain_1d", "rain_1d")):
            if col and col in X.columns:
                v = X[col].iloc[i]
                rec[key] = round(float(v), 3) if pd.notna(v) else None
        if a:
            rec.update({
                "expected": a.expected,
                "z_score": a.z_score,
                "severity": a.severity,
                "anomaly": a.severity not in ("NORMAL",),
            })
        rec["rain_mm"] = rain_by_date.get(d)
        out.append(rec)
    return out


def build_station_payloads(obs_all=None):
    """Score every station and assemble its payload. Returns (stations, series)."""
    obs_all = load_observations() if obs_all is None else obs_all
    stations, series = [], {}

    for st in STATIONS:
        obs, X = station_frame(st, obs_all)
        entry = {
            "id": st.id, "name": st.name, "lat": st.lat, "lon": st.lon,
            "role": st.role, "order": st.order, "description": st.description,
            "radius_m": st.radius_m,
            "upstream_of": st.upstream_of, "downstream_of": st.downstream_of,
            "observations": 0, "latest": None, "status": "NO_DATA",
            "model": None, "assessment": None,
        }
        if obs.empty:
            stations.append(entry)
            series[st.id] = []
            continue

        entry["observations"] = int(len(obs))
        up = upstream_neighbour(st)

        expected = z = scores = flags = pct = thresholds = None
        bundle = None
        try:
            bundle = load_bundle(st.id, features=FEATURE_COLUMNS)
        except ModelIncompatible as ex:
            entry["model_error"] = str(ex)

        if bundle is not None:
            base = bundle.estimators.get("baseline")
            anom = bundle.estimators.get("anomaly")
            if base is not None:
                # expected_for, not predict: over the training period the raw
                # model is recalling rows it was fitted on, which would show
                # nine silent years and then alerts starting the month training
                # stopped. This asks what was expected of each date at the time.
                expected = base.expected_for(X, obs["date"])
                z = (obs["ndti"].to_numpy(float) - expected) / (base.residual_std_ or 1e-6)
                thresholds = getattr(base, "residual_thresholds_", None)
            if anom is not None:
                scores = anom.score(X)
                flags = anom.flag(X) if anom.threshold_ is not None else None
                pct = [anom.percentile_of(s) for s in scores]
            md = bundle.metadata()
            entry["model"] = {
                "model_version": md["model_version"],
                "feature_version": md["feature_version"],
                "algorithm": md["algorithm"],
                "n_features": len(md["features"]),
                "training_start": md["training_start"],
                "training_end": md["training_end"],
                "validation_start": md["validation_start"],
                "validation_end": md["validation_end"],
                "test_start": md["test_start"],
                "test_end": md["test_end"],
                "training_rows": md["training_rows"],
                "validation_rows": md["validation_rows"],
                "test_rows": md["test_rows"],
                "created_at": md["created_at"],
                "validation_metrics": md["validation_metrics"],
                "test_metrics": md["test_metrics"],
                "features": md["features"],
            }

        assessments = assess_series(
            st, obs, X, expected=expected, z_scores=z,
            anomaly_scores=scores, anomaly_flags=flags, percentiles=pct,
            upstream_id=up.id if up else None, thresholds=thresholds)

        rain = load_rainfall(st.id)
        series[st.id] = _series_records(obs, X, assessments, rain)

        last = assessments[-1] if assessments else None
        if last:
            entry["status"] = last.severity
            entry["assessment"] = last.to_dict()
            entry["latest"] = {
                "date": last.date, "indicator": last.indicator,
                "expected": last.expected, "z_score": last.z_score,
                "quality": last.quality, "confidence": last.confidence,
                "rain_7d": last.rain_7d, "rain_context": last.rain_context,
            }
        stations.append(entry)
    return stations, series


def export_all(out_dir=WEB_DATA_DIR):
    os.makedirs(out_dir, exist_ok=True)
    obs_all = load_observations()
    stations, series = build_station_payloads(obs_all)

    # ---- alert feed: everything that is not NORMAL, newest first ----------
    alerts = []
    for sid, rows in series.items():
        st = BY_ID[sid]
        for r in rows:
            if r.get("severity") and r["severity"] != "NORMAL":
                alerts.append({
                    "station_id": sid, "station_name": st.name,
                    "date": r["date"], "severity": r["severity"],
                    "indicator": r["indicator"], "expected": r.get("expected"),
                    "z_score": r.get("z_score"), "rain_7d": r.get("rain_7d"),
                    "quality": r.get("quality"),
                })
    alerts.sort(key=lambda a: (a["date"], a["station_id"]), reverse=True)

    # detailed narratives only for the most recent assessment per station
    detailed = [s["assessment"] for s in stations
                if s.get("assessment") and s["assessment"]["severity"] != "NORMAL"]

    active = [a for a in alerts if a["severity"] in ("ELEVATED", "HIGH", "CRITICAL")]
    latest_dates = [s["latest"]["date"] for s in stations if s.get("latest")]

    # ---- catchment rainfall: mean of the last 7 days across stations ------
    rain_vals = [s["latest"]["rain_7d"] for s in stations
                 if s.get("latest") and s["latest"].get("rain_7d") is not None]

    ind_vals = [s["latest"]["indicator"] for s in stations if s.get("latest")]

    gt = load_ground_truth()
    summary = {
        "generated_at": _now(),
        "indicator": {"name": INDICATOR_NAME, "short": INDICATOR_SHORT,
                      "note": INDICATOR_NOTE, "unit": "index (dimensionless)"},
        "stations_total": len(stations),
        "stations_with_data": sum(1 for s in stations if s["observations"]),
        "observations_total": int(len(obs_all)),
        "latest_observation": max(latest_dates) if latest_dates else None,
        "mean_indicator": round(float(np.mean(ind_vals)), 4) if ind_vals else None,
        "mean_rain_7d_mm": round(float(np.mean(rain_vals)), 1) if rain_vals else None,
        "active_alerts": len(active),
        "alerts_by_severity": {
            s: sum(1 for a in alerts if a["severity"] == s)
            for s in ("WATCH", "ELEVATED", "HIGH", "CRITICAL")},
        "ground_truth_records": int(len(gt)),
        "calibrated_to_ntu": bool(len(gt)),
        "data_sources": read_json("data/sources/probe_evidence.json", {}),
    }

    write_json(os.path.join(out_dir, "summary.json"), summary)
    write_json(os.path.join(out_dir, "stations.json"), stations)
    write_json(os.path.join(out_dir, "series.json"), series)
    write_json(os.path.join(out_dir, "alerts.json"),
               {"alerts": alerts[:2000], "detailed": detailed})
    write_json(os.path.join(out_dir, "network.json"), load_network() or {})

    river = load_river()
    if river:
        write_json(os.path.join(out_dir, "river.geojson"), river)

    print(f"exported to {out_dir}:")
    print(f"  stations   {len(stations)} ({summary['stations_with_data']} with data)")
    print(f"  observations {summary['observations_total']}")
    print(f"  alerts     {len(alerts)} ({summary['active_alerts']} active)")
    print(f"  river      {'yes' if river else 'MISSING (run hydrology fetch)'}")
    return summary


def main():
    export_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

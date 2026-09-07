"""
In-situ water-quality ground truth: schema, validation, and satellite matching.

THERE IS CURRENTLY NO GROUND-TRUTH DATA IN THIS REPOSITORY.

That is a finding, not an oversight. We searched for an anonymous, programmatic
source of Ghanaian in-situ water-quality measurements and found none (evidence in
data/sources/probe_evidence.json):

  * data.gov.gh          — connection refused; the portal appears to be offline.
  * GEMStat (UNEP)       — the portal loads, but data requires a manual request
                           form. No anonymous API.
  * Water Quality Portal — a working public API, but United States only. It is
                           retained here purely as the SCHEMA reference that the
                           columns below imitate, so that any data later obtained
                           lands in a recognisable, standard shape.
  * Ghana Water Company, Water Research Institute, EPA Ghana — no open data API
                           found.

So this module implements the *path* for ground truth rather than the data. Drop
a CSV matching SCHEMA_COLUMNS into data/groundtruth/ and the supervised
calibration model (Model C) becomes trainable automatically. Until then the
system reports a satellite-derived ANOMALY INDICATOR and must never present a
number as if it were a measured NTU.

Never fabricate rows in this directory.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

GROUNDTRUTH_DIR = "data/groundtruth"
TEMPLATE_PATH = os.path.join(GROUNDTRUTH_DIR, "TEMPLATE.csv")

# Column names mirror Water Quality Portal conventions where sensible.
SCHEMA_COLUMNS = [
    "sample_date",        # YYYY-MM-DD (required)
    "station_id",         # must match a station in pipeline/config.py (required)
    "characteristic",     # turbidity | tss | conductivity | ph  (required)
    "value",              # numeric (required)
    "unit",               # NTU | FNU | mg/L | uS/cm            (required)
    "latitude",           # optional; defaults to the station coordinate
    "longitude",
    "depth_m",
    "method",             # e.g. "nephelometric", "gravimetric"
    "organisation",       # who measured it (required for provenance)
    "source_url",         # where it came from (required for provenance)
    "notes",
]

REQUIRED = ["sample_date", "station_id", "characteristic", "value", "unit",
            "organisation", "source_url"]

VALID_CHARACTERISTICS = {"turbidity", "tss", "conductivity", "ph"}
VALID_UNITS = {"NTU", "FNU", "mg/L", "uS/cm", "pH"}


@dataclass
class GroundTruthRecord:
    sample_date: date
    station_id: str
    characteristic: str
    value: float
    unit: str
    organisation: str
    source_url: str


def load_ground_truth(directory=GROUNDTRUTH_DIR):
    """Load every ground-truth CSV in `directory`, excluding the template.

    Returns an empty frame with the right columns when there is no data, so
    callers can branch on `.empty` rather than on a missing file.
    """
    empty = pd.DataFrame(columns=SCHEMA_COLUMNS)
    if not os.path.isdir(directory):
        return empty

    frames = []
    for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        if os.path.basename(path).upper().startswith("TEMPLATE"):
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty:
            continue
        df["_source_file"] = os.path.basename(path)
        frames.append(df)

    if not frames:
        return empty
    out = pd.concat(frames, ignore_index=True)
    out["sample_date"] = pd.to_datetime(out["sample_date"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna(subset=["sample_date", "value"]).reset_index(drop=True)


def validate_ground_truth(df, known_station_ids=None):
    """Return a list of problems. Empty list means the data is usable."""
    problems = []
    if df is None or df.empty:
        return ["no ground-truth records found"]

    for col in REQUIRED:
        if col not in df.columns:
            problems.append(f"missing required column: {col}")
    if problems:
        return problems

    if df[REQUIRED].isna().any().any():
        bad = df[REQUIRED].isna().any(axis=1).sum()
        problems.append(f"{bad} row(s) have empty required fields")

    unknown = set(df["characteristic"].str.lower().dropna()) - VALID_CHARACTERISTICS
    if unknown:
        problems.append(f"unrecognised characteristic(s): {sorted(unknown)}")

    bad_units = set(df["unit"].dropna()) - VALID_UNITS
    if bad_units:
        problems.append(f"unrecognised unit(s): {sorted(bad_units)}")

    if known_station_ids is not None:
        missing = set(df["station_id"].dropna()) - set(known_station_ids)
        if missing:
            problems.append(f"station_id not in the monitoring network: {sorted(missing)}")

    if (df["value"] < 0).any():
        problems.append("negative measurement values present")

    return problems


def match_to_observations(gt_df, obs_df, station_id, max_days=1,
                          characteristic="turbidity"):
    """Pair in-situ samples with satellite observations at the same station.

    A satellite pass and a field sample rarely coincide exactly, so a tolerance
    is allowed -- but it is deliberately tight (1 day by default). Turbidity can
    change within hours, so a loose window would pair measurements that describe
    genuinely different river states and quietly weaken any calibration built
    on them.
    """
    if gt_df is None or gt_df.empty or obs_df is None or obs_df.empty:
        return pd.DataFrame()

    gt = gt_df[(gt_df["station_id"] == station_id)
               & (gt_df["characteristic"].str.lower() == characteristic)].copy()
    if gt.empty:
        return pd.DataFrame()

    obs = obs_df.copy()
    obs["date"] = pd.to_datetime(obs["date"])
    obs_days = obs["date"].values.astype("datetime64[D]").astype(int)

    rows = []
    for _, g in gt.iterrows():
        gday = np.datetime64(g["sample_date"], "D").astype(int)
        diffs = np.abs(obs_days - gday)
        j = int(np.argmin(diffs))
        if diffs[j] <= max_days:
            rec = obs.iloc[j].to_dict()
            rec.update({
                "gt_value": float(g["value"]),
                "gt_unit": g["unit"],
                "gt_date": g["sample_date"],
                "gt_organisation": g.get("organisation"),
                "day_offset": int(diffs[j]),
            })
            rows.append(rec)
    return pd.DataFrame(rows)


def write_template(path=TEMPLATE_PATH):
    """Write an empty, documented CSV template. Contains NO data rows."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        fh.write(",".join(SCHEMA_COLUMNS) + "\n")
    return path

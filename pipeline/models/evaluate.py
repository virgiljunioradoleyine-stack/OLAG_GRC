"""
Scientific evaluation, and the gate that decides whether models may publish.

Reports what can honestly be measured. With no ground truth there are no
turbidity accuracy figures, and inventing proxy ones would be worse than
reporting none, so this measures what genuinely exists: how well the
expected-condition model generalises to unseen time periods, and how stable the
anomaly detector's flag rate is outside its training window.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..config import STATIONS
from ..features.builder import FEATURE_COLUMNS
from ..groundtruth.store import load_ground_truth
from ..io.atomic import write_json
from ..models.splits import DEFAULT_SPLIT, chronological_split
from ..models.train import station_frame
from ..models.versioning import ModelIncompatible, bundle_path, load_bundle
from ..satellite.observations import load_observations

EVAL_DIR = "data/evaluation"
EVAL_PATH = os.path.join(EVAL_DIR, "evaluation.json")

# Publication gate. A model that cannot beat "assume the last 30 days repeat"
# is not adding anything and should not be published.
MIN_SKILL_VS_NAIVE = 0.0
MAX_TEST_FLAG_RATE = 0.35


def evaluate_station(station, obs_all):
    obs, X = station_frame(station, obs_all)
    if obs.empty:
        return {"station_id": station.id, "status": "no observations"}
    try:
        bundle = load_bundle(station.id, features=FEATURE_COLUMNS)
    except ModelIncompatible as ex:
        return {"station_id": station.id, "status": "incompatible", "error": str(ex)}
    if bundle is None:
        return {"station_id": station.id, "status": "no model"}

    keep = obs["quality"].isin(["GOOD", "ACCEPTABLE", "LOW_QUALITY"]).to_numpy()
    obs, X = obs[keep].reset_index(drop=True), X[keep].reset_index(drop=True)
    tr, va, te = chronological_split(obs, DEFAULT_SPLIT)
    y = obs["ndti"].to_numpy(dtype=float)

    base = bundle.estimators.get("baseline")
    anom = bundle.estimators.get("anomaly")

    out = {
        "station_id": station.id, "station_name": station.name,
        "status": "evaluated",
        "model_version": bundle.model_version,
        "feature_version": bundle.feature_version,
        "training_period": [bundle.training_start, bundle.training_end],
        "validation_period": [bundle.validation_start, bundle.validation_end],
        "test_period": [bundle.test_start, bundle.test_end],
        "rows": {"train": int(tr.sum()), "validation": int(va.sum()), "test": int(te.sum())},
    }

    if base is not None:
        out["baseline"] = {
            "train": base.evaluate(X[tr], y[tr]) if tr.sum() > 3 else None,
            "validation": base.evaluate(X[va], y[va]) if va.sum() > 3 else None,
            "test": base.evaluate(X[te], y[te]) if te.sum() > 3 else None,
        }
        # error by season and by rainfall regime, on the test period
        if te.sum() > 6:
            resid = np.abs(base.residuals(X[te], y[te]))
            month = obs["date"][te].dt.month.to_numpy()
            season = np.where(np.isin(month, [12, 1, 2, 3]), "dry",
                              np.where(np.isin(month, [4, 5, 6, 7]), "wet_major", "wet_minor"))
            out["baseline"]["error_by_season"] = {
                s: round(float(np.nanmean(resid[season == s])), 5)
                for s in np.unique(season) if np.isfinite(resid[season == s]).any()}
            r7 = X["rain_7d"].to_numpy(dtype=float)[te]
            if np.isfinite(r7).any():
                hi = r7 >= np.nanmedian(r7)
                out["baseline"]["error_by_rainfall"] = {
                    "wetter_half": round(float(np.nanmean(resid[hi])), 5),
                    "drier_half": round(float(np.nanmean(resid[~hi])), 5)}

    if anom is not None and anom.threshold_ is not None:
        rates = {}
        for name, m in (("train", tr), ("validation", va), ("test", te)):
            if m.sum():
                rates[name] = round(float(anom.flag(X[m]).mean()), 4)
        out["anomaly"] = {
            "threshold": round(float(anom.threshold_), 6),
            "threshold_source": anom.threshold_source_,
            "flag_rate": rates,
            "stability": (
                round(abs(rates.get("validation", 0) - rates.get("test", 0)), 4)
                if "validation" in rates and "test" in rates else None),
        }
    return out


def gate(results):
    """Return (ok, reasons). Publication is refused when a model is unsound."""
    reasons = []
    evaluated = [r for r in results if r.get("status") == "evaluated"]
    if not evaluated:
        return False, ["no station produced an evaluable model"]

    for r in results:
        if r.get("status") == "incompatible":
            reasons.append(f"{r['station_id']}: model incompatible with the feature contract")

    for r in evaluated:
        b = (r.get("baseline") or {}).get("test") or (r.get("baseline") or {}).get("validation")
        if b and b.get("skill_vs_naive") is not None:
            if b["skill_vs_naive"] < MIN_SKILL_VS_NAIVE:
                reasons.append(
                    f"{r['station_id']}: baseline has no skill over a naive "
                    f"30-day mean (skill={b['skill_vs_naive']})")
        a = r.get("anomaly") or {}
        tr = (a.get("flag_rate") or {}).get("test")
        if tr is not None and tr > MAX_TEST_FLAG_RATE:
            reasons.append(
                f"{r['station_id']}: flags {tr:.0%} of the test period, which is "
                f"implausible as an alert rate")
    return (not reasons), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero if any model fails the publication gate")
    args = ap.parse_args()

    obs_all = load_observations()
    results = [evaluate_station(s, obs_all) for s in STATIONS]
    ok, reasons = gate(results)
    gt = load_ground_truth()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": DEFAULT_SPLIT.describe(),
        "ground_truth_records": int(len(gt)),
        "supervised_metrics_available": bool(len(gt)),
        "note": (
            "No in-situ water-quality measurements are available, so no "
            "turbidity accuracy metrics (MAE/RMSE against NTU) can be computed. "
            "What is reported is how well the expected-condition model "
            "generalises to unseen time periods, and how stable the anomaly "
            "flag rate is outside its calibration window."),
        "gate_passed": ok,
        "gate_reasons": reasons,
        "stations": results,
    }
    os.makedirs(EVAL_DIR, exist_ok=True)
    write_json(EVAL_PATH, report)
    write_markdown(report)

    print(f"evaluation -> {EVAL_PATH} and {EVAL_MD}")
    for r in results:
        if r.get("status") != "evaluated":
            print(f"  {r['station_id']}: {r.get('status')}")
            continue
        b = (r.get("baseline") or {}).get("test") or {}
        a = r.get("anomaly") or {}
        print(f"  {r['station_id']}: test MAE={b.get('mae')} "
              f"skill={b.get('skill_vs_naive')} "
              f"flag_rate={(a.get('flag_rate') or {}).get('test')}")
    print(f"\ngate: {'PASS' if ok else 'FAIL'}")
    for x in reasons:
        print(f"  - {x}")
    return 0 if (ok or not args.gate) else 1



# ------------------------------------------------------------- markdown ---

EVAL_MD = "EVALUATION.md"


def write_markdown(report, path=EVAL_MD):
    """Render the evaluation as a document, regenerated from the JSON.

    Written by the same code that computes the numbers so the prose cannot
    drift away from the results -- the audit found documentation quoting
    figures from a model that no longer existed.
    """
    from ..io.atomic import atomic_write

    ev = [r for r in report["stations"] if r.get("status") == "evaluated"]
    lines = [
        "# Evaluation",
        "",
        f"Generated {report['generated_at']} by `python -m pipeline.models.evaluate`.",
        "Do not edit by hand — this file is regenerated from",
        "`data/evaluation/evaluation.json`.",
        "",
        "## What can and cannot be measured",
        "",
        report["note"],
        "",
        f"**Ground-truth records available: {report['ground_truth_records']}.** "
        + ("Supervised turbidity metrics are therefore reported below."
           if report["supervised_metrics_available"] else
           "No MAE, RMSE or R² against measured turbidity can be reported, "
           "because no measured turbidity exists for this basin. Reporting such "
           "figures would require inventing the measurements."),
        "",
        "## Validation design",
        "",
        f"`{report['split']}`",
        "",
        "Chronological, never shuffled. Preprocessing is fitted on the training",
        "period alone; thresholds are chosen on validation; the test period is",
        "untouched until this report.",
        "",
        "## Expected-condition model (Model B)",
        "",
        "`skill` is the fractional improvement in mean absolute error over a naive",
        "predictor that assumes the last 30 days repeat. Positive means the model",
        "adds information; zero or below means it does not.",
        "",
        "| Station | Train | Val | Test | Test MAE | Test RMSE | Skill vs naive |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in ev:
        t = (r.get("baseline") or {}).get("test") or {}
        rows = r["rows"]
        lines.append(
            f"| {r['station_id']} {r['station_name']} | {rows['train']} | "
            f"{rows['validation']} | {rows['test']} | {t.get('mae', '—')} | "
            f"{t.get('rmse', '—')} | {t.get('skill_vs_naive', '—')} |")

    lines += ["", "### Error by season (test period, mean absolute residual)", "",
              "| Station | " + " | ".join(["dry", "wet major", "wet minor"]) + " |",
              "|---|---|---|---|"]
    for r in ev:
        s = (r.get("baseline") or {}).get("error_by_season") or {}
        lines.append(f"| {r['station_id']} | {s.get('dry','—')} | "
                     f"{s.get('wet_major','—')} | {s.get('wet_minor','—')} |")

    lines += ["", "### Error by rainfall regime (test period)", "",
              "| Station | Wetter half | Drier half |", "|---|---|---|"]
    for r in ev:
        s = (r.get("baseline") or {}).get("error_by_rainfall") or {}
        lines.append(f"| {r['station_id']} | {s.get('wetter_half','—')} | "
                     f"{s.get('drier_half','—')} |")

    lines += ["", "## Anomaly detector (Model A)", "",
              "The threshold is calibrated on the validation period, not set by a",
              "`contamination` argument. `stability` is the absolute difference",
              "between validation and test flag rates — small is good, and means the",
              "detector behaves the same on data it has never seen.", "",
              "| Station | Threshold | Source | Train | Val | Test | Stability |",
              "|---|---|---|---|---|---|---|"]
    for r in ev:
        a = r.get("anomaly") or {}
        fr = a.get("flag_rate") or {}
        lines.append(
            f"| {r['station_id']} | {a.get('threshold','—')} | "
            f"{(a.get('threshold_source') or '—').split('(')[0].strip()} | "
            f"{fr.get('train','—')} | {fr.get('validation','—')} | "
            f"{fr.get('test','—')} | {a.get('stability','—')} |")

    lines += ["", "## Publication gate", "",
              f"**{'PASS' if report['gate_passed'] else 'FAIL'}**", ""]
    if report["gate_reasons"]:
        lines += ["Reasons:", ""] + [f"- {x}" for x in report["gate_reasons"]] + [""]
    else:
        lines += ["Every model beat the naive baseline and produced a plausible "
                  "flag rate on the held-out test period.", ""]

    lines += [
        "## Limitations",
        "",
        "- **No calibration to NTU or TSS.** The index is dimensionless. Nothing",
        "  in this system converts it to a concentration, and it must not be",
        "  presented as one.",
        "- **Skill is measured against a naive baseline, not against truth.** A",
        "  model can predict the index well while the index itself is a poor proxy",
        "  for water quality. Only ground-truth measurements can settle that.",
        "- **Irregular sampling.** Cloud decides when observations exist, so test",
        "  periods contain fewer rows than a regular time series would.",
        "- **Single basin.** Eight stations on one river. No claim of",
        "  generalisation to other rivers is supported.",
        "",
    ]
    with atomic_write(path) as fh:
        fh.write("\n".join(lines))
    return path


if __name__ == "__main__":
    raise SystemExit(main())

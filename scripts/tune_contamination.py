#!/usr/bin/env python3
"""
STEP 2 — compare contamination values for the Isolation Forest.

`contamination` tells the forest what fraction of training data to treat as
anomalous, which sets the alert threshold. Too high and we cry wolf; too low and
we miss real events. This scores each candidate on the historical record and
reports what actually gets flagged, so the choice is evidence-based rather than
a default left in place.

The key column is CLEAN: flagged dates where the control point did NOT rise.
Those are the ones that look like pollution rather than rainfall.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from pipeline.alerts import CONTROL_RISE_THRESHOLD  # noqa: E402
from pipeline.model import build_features, load_readings, train  # noqa: E402

CANDIDATES = [0.02, 0.05, 0.10]


def evaluate(point_id, contamination):
    model, df, X = train(point_id, contamination=contamination)
    scores = model.forest.score_samples(model.scaler.transform(X))
    pred = model.forest.predict(model.scaler.transform(X))
    flagged = np.nonzero(pred == -1)[0]

    rows = []
    for i in flagged:
        cd = X["control_delta"].iloc[i]
        rows.append({
            "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
            "ndti": df["ndti"].iloc[i],
            "delta": X["ndti_delta"].iloc[i],
            "control_delta": cd,
            "clean": bool(cd < CONTROL_RISE_THRESHOLD),
            "rising": bool(X["ndti_delta"].iloc[i] > 0),
            "score": scores[i],
        })
    return model, df, rows


def main():
    point_ids = sys.argv[1:] or ["monitor", "intake"]
    for pid in point_ids:
        try:
            n = len(load_readings(pid))
        except FileNotFoundError:
            print(f"\n### {pid}: no readings CSV, skipping")
            continue
        print(f"\n{'='*72}\n{pid.upper()}  ({n} historical readings)\n{'='*72}")
        for c in CANDIDATES:
            model, df, rows = evaluate(pid, c)
            clean = [r for r in rows if r["clean"]]
            alerts = [r for r in clean if r["rising"]]
            years = 9.7
            print(f"\ncontamination = {c:.2f}  ->  {len(rows)} flagged "
                  f"({100*len(rows)/max(n,1):.0f}%), {len(clean)} with a flat "
                  f"control, {len(alerts)} of those RISING = real ALERTs "
                  f"({len(alerts)/years:.1f}/year)")
            for r in sorted(rows, key=lambda r: r["date"]):
                tag = ("ALERT " if (r["clean"] and r["rising"])
                       else "fell  " if r["clean"] else "rain? ")
                print(f"    {tag} {r['date']}  ndti={r['ndti']:+.4f} "
                      f"delta={r['delta']:+.4f} control_delta={r['control_delta']:+.4f}"
                      f"  score={r['score']:.4f}")


if __name__ == "__main__":
    main()

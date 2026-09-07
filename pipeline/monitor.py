"""
STEP 4 — the scheduled monitoring run.

Fetches only what is new since the last reading in each CSV, scores it with the
trained Isolation Forest, writes the alert text, and appends everything back to
the repo's data files. Those files are the database, so this is our write.

Features for a new reading are computed by rebuilding the feature table over the
whole updated series and taking the last row, rather than computing the new row
in isolation. That guarantees the rolling baselines and control matching are
derived exactly the same way they were at training time -- if the two ever drift
apart, the model is being asked about a different kind of thing than it learned.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from .alerts import describe
from .fetch import FIELDS, collect, write_csv
from .model import build_features, load, load_readings
from .points import POINTS

ALERTS_PATH = "data/alerts.json"
LOOKBACK_DAYS = 30          # how far back a scheduled run looks for new scenes
MAX_ALERTS = 500


def last_date(point_id):
    try:
        df = load_readings(point_id)
    except FileNotFoundError:
        return None
    return None if df.empty else df["date"].max().date()


def update_point(point, start):
    """Collect new readings for one point and merge them into its CSV."""
    fresh = collect(point, start=start, verbose=False)
    if not fresh:
        return 0, None

    path = f"data/readings/{point['id']}.csv"
    existing = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=FIELDS)
    merged = pd.concat([existing, pd.DataFrame(fresh)], ignore_index=True)
    merged = (merged.sort_values(["date", "water_pixel_count"])
                    .drop_duplicates("date", keep="last")
                    .sort_values("date"))
    added = len(merged) - len(existing)
    write_csv(point["id"], merged.to_dict("records"))
    return added, merged


def score_latest(point, control_df):
    """Score this point's most recent reading. None for the control point."""
    df = load_readings(point["id"])
    if df.empty:
        return None
    X = build_features(df, control_df)
    model = load(point["id"])
    row = X.iloc[-1].to_numpy()
    prediction, score = model.score(row)
    return describe(
        point_name=point["name"],
        date=df["date"].iloc[-1].strftime("%Y-%m-%d"),
        ndti=df["ndti"].iloc[-1],
        prediction=prediction,
        score=score,
        percentile=model.percentile_of(score),
        control_delta=float(X["control_delta"].iloc[-1]),
        control_ndti=float(X["control_ndti"].iloc[-1]),
    )


def main():
    os.environ.setdefault("GDAL_DISABLE_READ_DIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

    # control first: the other points' features depend on it
    ordered = sorted(POINTS, key=lambda p: p["role"] != "control")
    for p in ordered:
        seen = last_date(p["id"])
        start = (seen - timedelta(days=1)) if seen else date(2017, 1, 1)
        start = max(start, date.today() - timedelta(days=LOOKBACK_DAYS)) if seen else start
        added, _ = update_point(p, start)
        print(f"{p['id']}: +{added} readings (from {start})")

    control_df = load_readings("control")
    alerts = []
    if os.path.exists(ALERTS_PATH):
        with open(ALERTS_PATH) as fh:
            alerts = json.load(fh)
    known = {(a["point"], a["date"]) for a in alerts}

    for p in POINTS:
        if p["role"] == "control":
            continue
        if not os.path.exists(f"models/{p['id']}.pkl"):
            print(f"{p['id']}: no trained model, skipping scoring")
            continue
        a = score_latest(p, control_df)
        if not a:
            continue
        print(f"{p['id']}: {a['tier']} — {a['date']}")
        # the feed carries things worth reading; NORMAL readings live in the
        # chart, and appending them would bury the alerts under routine days
        if a["tier"] != "NORMAL" and (a["point"], a["date"]) not in known:
            a["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            alerts.append(a)

    alerts.sort(key=lambda a: (a["date"], a["point"]), reverse=True)
    os.makedirs("data", exist_ok=True)
    with open(ALERTS_PATH, "w") as fh:
        json.dump(alerts[:MAX_ALERTS], fh, indent=2)
    print(f"wrote {ALERTS_PATH} ({len(alerts[:MAX_ALERTS])} entries)")


if __name__ == "__main__":
    main()

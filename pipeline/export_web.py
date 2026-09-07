"""
Export the pipeline's data as a single JSON file the dashboard reads.

The dashboard lives in web/ and is deployed with that as its root directory, so
rather than have it reach up into the repo for CSVs, we write a self-contained
snapshot into web/public/data/. The dashboard then has no build-time dependency
on the pipeline's layout, and the file is versioned in the repo like everything
else.
"""
from __future__ import annotations

import json
import os

import numpy as np

from .model import FEATURES, build_features, load, load_readings
from .points import POINTS, mgrs_tile

OUT = "web/public/data/dashboard.json"


def _series(point_id):
    try:
        df = load_readings(point_id)
    except FileNotFoundError:
        return []
    return [
        {
            "date": r["date"].strftime("%Y-%m-%d"),
            "ndti": round(float(r["ndti"]), 5),
            "cloud": None if r["cloud_cover"] != r["cloud_cover"] else round(float(r["cloud_cover"]), 1),
            "pixels": int(r["water_pixel_count"]),
        }
        for _, r in df.iterrows()
    ]


def build():
    control_df = None
    try:
        control_df = load_readings("control")
    except FileNotFoundError:
        pass

    points = []
    for p in POINTS:
        z, b, sq = mgrs_tile(p["lat"], p["lon"])
        entry = {
            "id": p["id"], "name": p["name"], "role": p["role"],
            "lat": p["lat"], "lon": p["lon"], "tile": f"T{z}{b}{sq}",
            "readings": _series(p["id"]),
            "anomalies": [],
            "model": None,
        }
        model_path = f"models/{p['id']}.pkl"
        if p["role"] != "control" and os.path.exists(model_path):
            m = load(p["id"])
            df = load_readings(p["id"])
            X = build_features(df, control_df)
            Xs = m.scaler.transform(X)
            pred = m.forest.predict(Xs)
            scores = m.forest.score_samples(Xs)
            entry["anomalies"] = [
                {"date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                 "ndti": round(float(df["ndti"].iloc[i]), 5),
                 "score": round(float(scores[i]), 5)}
                for i in np.nonzero(pred == -1)[0]
            ]
            entry["model"] = {
                "trees": int(m.forest.n_estimators),
                "samples": int(m.n_samples),
                "contamination": float(m.contamination),
                "features": list(m.features),
            }
        points.append(entry)

    alerts = []
    if os.path.exists("data/alerts.json"):
        with open("data/alerts.json") as fh:
            alerts = json.load(fh)

    return {
        "points": points,
        "alerts": alerts,
        "features": list(FEATURES),
        "generated_at": __import__("datetime").datetime.utcnow()
                        .isoformat(timespec="seconds") + "Z",
    }


def main():
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(data, fh, indent=2)
    n = sum(len(p["readings"]) for p in data["points"])
    print(f"wrote {OUT}: {len(data['points'])} points, {n} readings, "
          f"{len(data['alerts'])} alerts")


if __name__ == "__main__":
    main()

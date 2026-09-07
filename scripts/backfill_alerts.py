#!/usr/bin/env python3
"""
Score every historical reading and write data/alerts.json.

The scheduled job only scores the newest reading. This replays the whole record
through the same model and the same alert rules, which gives the dashboard a
real feed to show and gives the notebook a defensible answer to "what would this
system have said, and when".
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.alerts import describe  # noqa: E402
from pipeline.model import build_features, load, load_readings  # noqa: E402
from pipeline.points import POINTS  # noqa: E402

OUT = "data/alerts.json"


def main():
    control = load_readings("control")
    alerts = []
    for p in POINTS:
        if p["role"] == "control" or not os.path.exists(f"models/{p['id']}.pkl"):
            continue
        df = load_readings(p["id"])
        X = build_features(df, control)
        m = load(p["id"])
        Xs = m.scaler.transform(X)
        preds = m.forest.predict(Xs)
        scores = m.forest.score_samples(Xs)
        for i in range(len(df)):
            a = describe(
                point_name=p["name"],
                date=df["date"].iloc[i].strftime("%Y-%m-%d"),
                ndti=df["ndti"].iloc[i],
                prediction=int(preds[i]),
                score=float(scores[i]),
                percentile=m.percentile_of(float(scores[i])),
                control_delta=float(X["control_delta"].iloc[i]),
                control_ndti=float(X["control_ndti"].iloc[i]),
                ndti_delta=float(X["ndti_delta"].iloc[i]),
            )
            alerts.append(a)

    # the feed shows things worth reading; NORMAL readings live in the chart
    feed = [a for a in alerts if a["tier"] != "NORMAL"]
    feed.sort(key=lambda a: (a["date"], a["point"]), reverse=True)
    with open(OUT, "w") as fh:
        json.dump(feed, fh, indent=2)

    from collections import Counter
    print(f"scored {len(alerts)} readings -> {OUT} ({len(feed)} non-normal)")
    print("  ", dict(Counter(a["tier"] for a in alerts)))
    for a in feed[:6]:
        print(f"   {a['date']}  {a['tier']:8s} {a['point']}")


if __name__ == "__main__":
    main()

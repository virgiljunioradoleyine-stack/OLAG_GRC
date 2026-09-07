#!/usr/bin/env python3
"""Train and save an Isolation Forest for each monitored point."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.model import save, train  # noqa: E402
from pipeline.points import POINTS  # noqa: E402

CONTAMINATION = 0.05


def main():
    c = float(sys.argv[1]) if len(sys.argv) > 1 else CONTAMINATION
    for p in POINTS:
        if p["role"] == "control":
            continue
        model, df, X = train(p["id"], contamination=c)
        path = save(model)
        n_flag = int((model.forest.predict(model.scaler.transform(X)) == -1).sum())
        print(f"{p['id']:8s} -> {path}  {model.n_samples} samples, "
              f"{model.forest.n_estimators} trees, contamination={c}, "
              f"{n_flag} historical readings flagged")


if __name__ == "__main__":
    main()

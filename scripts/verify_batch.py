#!/usr/bin/env python3
"""
Verify several candidate coordinates at once.

    python scripts/verify_batch.py "5.1449,-1.6528" "5.3453,-1.6208" ...

Same checks as verify_point.py, but scene searches are cached per tile so a
batch of candidates costs roughly one tile lookup instead of one per point.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.io.env import configure_gdal  # noqa: E402

configure_gdal()

import numpy as np  # noqa: E402

from pipeline.points import from_utm, mgrs_tile, to_utm  # noqa: E402
from pipeline.search import search  # noqa: E402
from pipeline.water import persistent_water, snap_to_channel  # noqa: E402

RADIUS = 50.0
N_SCENES = 12
_tiles = {}


def clearest(z, b, sq):
    key = (z, b, sq)
    if key not in _tiles:
        end = date.today()
        items = search(z, b, sq, end - timedelta(days=548), end, max_cloud=101)
        items.sort(key=lambda i: i["properties"]["eo:cloud_cover"])
        _tiles[key] = items[:N_SCENES]
        cc = [i["properties"]["eo:cloud_cover"] for i in _tiles[key]]
        print(f"[tile T{z}{b}{sq}: {len(items)} scenes, using {len(cc)} clearest "
              f"{cc[0]:.1f}%-{cc[-1]:.1f}% cloud]\n")
    return _tiles[key]


def check(lat, lon, label):
    z, b, sq = mgrs_tile(lat, lon)
    e, n, epsg = to_utm(lat, lon)
    scenes = clearest(z, b, sq)
    pw = persistent_water(scenes, e, n, half_m=1000.0)

    print(f"{label}  {lat:.6f}, {lon:.6f}   [T{z}{b}{sq}]")
    if pw is None:
        print("   ERROR: imagery unreadable here\n")
        return
    mask, tf = pw["mask"], pw["transform"]
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        print("   NO PERSISTENT WATER within 1 km\n")
        return

    xs = tf.c + (cols + 0.5) * tf.a
    ys = tf.f + (rows + 0.5) * tf.e
    d = np.hypot(xs - e, ys - n)
    n_px = int((d <= RADIUS).sum())
    k = int(np.argmin(d))
    la, lo = from_utm(xs[k], ys[k], epsg)

    verdict = ("GOOD" if n_px >= 8 else "MARGINAL" if n_px >= 3 else "OFF CHANNEL")
    print(f"   {verdict}: {n_px} px in {RADIUS:.0f} m window, "
          f"{len(rows)} px within 1 km")
    print(f"   nearest water {d[k]:.0f} m at {la:.5f}, {lo:.5f}")
    if n_px < 8:
        snap = snap_to_channel(pw, e, n, radius_m=RADIUS)
        if snap and snap[2] > n_px:
            sx, sy, cnt = snap
            sla, slo = from_utm(sx, sy, epsg)
            moved = np.hypot(sx - e, sy - n)
            print(f"   -> better: {sla:.5f}, {slo:.5f}  "
                  f"({cnt} px, {moved:.0f} m away)")
    print()


if __name__ == "__main__":
    for i, arg in enumerate(sys.argv[1:], 1):
        lat, lon = (float(x) for x in arg.replace(" ", "").split(","))
        check(lat, lon, f"#{i}")

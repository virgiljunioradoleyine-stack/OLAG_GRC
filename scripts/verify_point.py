#!/usr/bin/env python3
"""
Check whether a candidate coordinate actually sits on the river.

    python scripts/verify_point.py 6.2226 -1.6479
    python scripts/verify_point.py 6.2226 -1.6479 --label control --radius 50

Pick a coordinate on a satellite basemap, paste it here, and this tells you --
from real Sentinel-2 data, not a map tile -- whether it is on persistent water,
how many usable pixels a reading there would get, and if it is off the channel,
where the nearest water actually is.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.io.env import configure_gdal  # noqa: E402

configure_gdal()

import numpy as np  # noqa: E402

from pipeline.points import from_utm, mgrs_tile, to_utm  # noqa: E402
from pipeline.search import search  # noqa: E402
from pipeline.water import persistent_water  # noqa: E402

VERDICT_GOOD = 8      # usable water pixels for a solid reading
VERDICT_MARGINAL = 3  # bare minimum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    ap.add_argument("--label", default="candidate")
    ap.add_argument("--radius", type=float, default=50.0,
                    help="reading window radius in metres (default 50)")
    ap.add_argument("--scenes", type=int, default=12,
                    help="clearest scenes to build the water mask from")
    ap.add_argument("--months", type=int, default=18)
    a = ap.parse_args()

    z, b, sq = mgrs_tile(a.lat, a.lon)
    e, n, epsg = to_utm(a.lat, a.lon)
    print(f"\n{a.label}: {a.lat:.5f}, {a.lon:.5f}")
    print(f"  tile T{z}{b}{sq}   EPSG:{epsg}  E{e:.0f} N{n:.0f}")

    end = date.today()
    start = end - timedelta(days=int(a.months * 30.4))
    items = search(z, b, sq, start, end, max_cloud=101)
    if not items:
        print("  ERROR: no scenes found for this tile")
        return 2
    items.sort(key=lambda i: i["properties"]["eo:cloud_cover"])
    chosen = items[:a.scenes]
    print(f"  {len(items)} scenes available; using the {len(chosen)} clearest "
          f"({chosen[0]['properties']['eo:cloud_cover']:.1f}%"
          f"-{chosen[-1]['properties']['eo:cloud_cover']:.1f}% cloud)")

    pw = persistent_water(chosen, e, n, half_m=1000.0)
    if pw is None:
        print("  ERROR: could not read imagery here")
        return 2
    print(f"  water mask built from {pw['scenes_used']} scenes\n")

    mask, tf = pw["mask"], pw["transform"]
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        print("  VERDICT: NO PERSISTENT WATER within 1 km. Wrong spot entirely.")
        return 1

    xs = tf.c + (cols + 0.5) * tf.a
    ys = tf.f + (rows + 0.5) * tf.e
    dist = np.hypot(xs - e, ys - n)

    in_window = dist <= a.radius
    n_px = int(in_window.sum())
    print(f"  persistent-water pixels within {a.radius:.0f} m window: {n_px}")
    print(f"  persistent-water pixels within 1 km: {len(rows)}")

    k = int(np.argmin(dist))
    near_lat, near_lon = from_utm(xs[k], ys[k], epsg)
    print(f"  nearest persistent water: {dist[k]:.0f} m away "
          f"at {near_lat:.5f}, {near_lon:.5f}")

    if n_px >= VERDICT_GOOD:
        print(f"\n  VERDICT: GOOD -- on the river, {n_px} pixels per reading.")
        rc = 0
    elif n_px >= VERDICT_MARGINAL:
        print(f"\n  VERDICT: MARGINAL -- only {n_px} pixels. Readings will be "
              f"noisy. Try nudging onto a wider stretch.")
        rc = 0
    else:
        print(f"\n  VERDICT: OFF THE CHANNEL -- {n_px} usable pixels.")
        print(f"  Try instead: {near_lat:.5f}, {near_lon:.5f}")
        rc = 1

    obs = pw["observations"]
    print(f"  (clear observations per pixel, median: {int(np.median(obs))} "
          f"of {pw['scenes_used']} scenes)")
    return rc


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
STEP 0 — prove each part of the data stack works in isolation.

Run:  python scripts/step0_verify.py
Every number this prints is measured live, not cached.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta

os.environ.setdefault("GDAL_HTTP_CAINFO", "/root/.ccr/ca-bundle.crt")
os.environ.setdefault("GDAL_DISABLE_READ_DIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402

from pipeline.points import POINTS, mgrs_tile, to_utm  # noqa: E402
from pipeline.search import search  # noqa: E402
from pipeline.ndti import _vsicurl, ndti_at_point, read_point_window  # noqa: E402

results = {}


def head(n, title):
    print(f"\n{'='*70}\nCHECK {n} — {title}\n{'='*70}")


def check1():
    head(1, "Scene discovery (S3-backed, replaces blocked STAC search API)")
    end = date.today()
    start = end - timedelta(days=545)
    z, b, sq = mgrs_tile(POINTS[0]["lat"], POINTS[0]["lon"])
    print(f"tile for control point: T{z}{b}{sq}   window {start} .. {end}")

    t = time.time()
    items = search(z, b, sq, start, end, max_cloud=101)
    print(f"scenes found: {len(items)}  ({time.time()-t:.1f}s)")
    if not items:
        results[1] = ("FAIL", "no scenes returned")
        return None

    cc = sorted(i["properties"]["eo:cloud_cover"] for i in items)
    print(f"tile cloud cover  min={cc[0]:.1f}%  median={cc[len(cc)//2]:.1f}%  max={cc[-1]:.1f}%")
    print(f"scenes with tile cloud < 20%: {sum(1 for v in cc if v < 20)}  "
          f"<- why we filter per-pixel instead (see HICCUPS.md)")
    print("\n3 most recent scenes:")
    for it in items[-3:]:
        p = it["properties"]
        print(f"   {it['id']}   {p['datetime'][:10]}   cloud={p['eo:cloud_cover']:.2f}%")

    results[1] = ("PASS", f"{len(items)} scenes discoverable")
    return sorted(items, key=lambda i: i["properties"]["eo:cloud_cover"])[0]


def check2(item):
    head(2, "Asset retrieval (windowed COG read, no full download)")
    if item is None:
        results[2] = ("SKIP", "no scene from check 1")
        return
    print(f"using clearest scene: {item['id']} ({item['properties']['eo:cloud_cover']:.2f}% cloud)")
    for key in ("red", "green", "scl"):
        href = item["assets"][key]["href"]
        t = time.time()
        with rasterio.open(_vsicurl(href)) as ds:
            mb = ds.width * ds.height * np.dtype(ds.dtypes[0]).itemsize / 1e6
            print(f"   {key:6s} {href.rsplit('/',1)[-1]:10s} {ds.width}x{ds.height} "
                  f"{ds.dtypes[0]} res={ds.res[0]:.0f}m  full-file~{mb:.0f}MB  "
                  f"header read in {time.time()-t:.2f}s")
    results[2] = ("PASS", "COG headers readable via HTTP range requests")


def check3(item):
    head(3, "NDTI on real pixels")
    if item is None:
        results[3] = ("SKIP", "no scene from check 1")
        return
    p = POINTS[0]
    e, n, epsg = to_utm(p["lat"], p["lon"])
    print(f"point: {p['name']} ({p['lat']}, {p['lon']}) -> EPSG:{epsg} E{e:.0f} N{n:.0f}")

    w = read_point_window(item, e, n)
    import collections
    hist = dict(sorted(collections.Counter(w["scl"].ravel().tolist()).items()))
    print(f"window {w['red'].shape} @10m   red median={np.nanmedian(w['red']):.4f}  "
          f"green median={np.nanmedian(w['green']):.4f}")
    print(f"SCL classes present: {hist}   (6 = water)")

    r = ndti_at_point(item, e, n)
    if r["ndti"] is None:
        print(f"NDTI: NOT COMPUTABLE — {r['reason']}")
        print("  -> the point is not on water; see HICCUPS.md")
        results[3] = ("FAIL", r["reason"])
        return

    print(f"NDTI = {r['ndti']:.4f}  (from {r['water_pixel_count']} water pixels)")
    ok = -1.0 <= r["ndti"] <= 1.0
    print(f"sane range check (-1..1): {'PASS' if ok else 'FAIL'}")
    results[3] = ("PASS" if ok else "FAIL", f"NDTI={r['ndti']:.4f}")


def main():
    item = check1()
    check2(item)
    check3(item)

    print(f"\n{'='*70}\nSUMMARY\n{'='*70}")
    for n in (1, 2, 3):
        status, note = results.get(n, ("SKIP", ""))
        print(f"  check {n}: {status:5s}  {note}")
    print("  check 4: see .github/workflows/hello.yml (runs in CI)")
    print("  check 5: Vercel — see STEP0_REPORT.md")
    return 0 if all(results.get(n, ("FAIL",))[0] == "PASS" for n in (1, 2, 3)) else 1


if __name__ == "__main__":
    sys.exit(main())

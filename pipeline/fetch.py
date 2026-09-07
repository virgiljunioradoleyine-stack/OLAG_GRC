"""
STEP 1 — build the historical NDTI record for each monitoring point.

Design note: the water mask is computed ONCE per point from the clearest scenes
and then held fixed, rather than re-detecting water in every scene. This matters.
A heavy sediment plume changes a river's spectral signature, so per-scene water
detection would shrink the detected channel exactly when pollution is worst, and
we would end up sampling a different set of pixels on precisely the dates we care
about. A fixed channel mask keeps the sample consistent, so a change in NDTI
means a change in the water, not a change in where we looked.

Cloud rejection stays per-scene (via SCL), because clouds do move.
"""
from __future__ import annotations

import csv
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

from .ndti import _band_scaling, _vsicurl
from .points import POINTS, mgrs_tile, to_utm
from .search import search
from .water import SCL_CLOUDY, persistent_water

READING_RADIUS_M = 50.0
MASK_SCENES = 12
MIN_PIXELS = 3
HISTORY_DAYS = 548          # ~18 months


def _read_window(item, key, bounds, out_shape=None):
    scale, offset = _band_scaling(item, key)
    with rasterio.open(_vsicurl(item["assets"][key]["href"])) as ds:
        win = from_bounds(*bounds, transform=ds.transform).round_offsets().round_lengths()
        kw = {"out_shape": out_shape, "resampling": Resampling.nearest} if out_shape else {}
        arr = ds.read(1, window=win, **kw).astype("float32")
        arr[arr == 0] = np.nan
        return arr * scale + offset


def build_channel_mask(items, easting, northing):
    """Fixed channel mask on the 10 m grid, from the clearest scenes."""
    pw = persistent_water(items[:MASK_SCENES], easting, northing,
                          half_m=READING_RADIUS_M * 2)
    if pw is None or not pw["mask"].any():
        return None
    return pw


def reading_for_scene(item, easting, northing, mask20):
    """One NDTI reading, or None when the scene is unusable here."""
    bounds = (easting - READING_RADIUS_M, northing - READING_RADIUS_M,
              easting + READING_RADIUS_M, northing + READING_RADIUS_M)
    try:
        red = _read_window(item, "red", bounds)
        green = _read_window(item, "green", bounds, out_shape=red.shape)
        scl = _read_window(item, "scl", bounds, out_shape=red.shape)
    except Exception:
        return None

    # channel mask is on the 20 m grid; nearest-neighbour it onto the 10 m grid
    mh, mw = mask20.shape
    ry = np.clip((np.arange(red.shape[0]) * mh) // red.shape[0], 0, mh - 1)
    rx = np.clip((np.arange(red.shape[1]) * mw) // red.shape[1], 0, mw - 1)
    channel = mask20[np.ix_(ry, rx)]

    scl_raw = np.nan_to_num(scl, nan=0).astype("uint8")
    denom = red + green
    usable = (channel & np.isfinite(red) & np.isfinite(green)
              & (np.abs(denom) > 1e-6) & ~np.isin(scl_raw, list(SCL_CLOUDY)))

    n = int(usable.sum())
    if n < MIN_PIXELS:
        return None

    vals = ((red - green) / denom)[usable]
    p = item["properties"]
    return {
        "date": p["datetime"][:10],
        "ndti": round(float(np.median(vals)), 6),
        "ndti_std": round(float(np.std(vals)), 6),
        "cloud_cover": round(float(p.get("eo:cloud_cover", float("nan"))), 3),
        "scene_id": item["id"],
        "water_pixel_count": n,
    }


def collect(point, days=HISTORY_DAYS, workers=8, verbose=True):
    z, b, sq = mgrs_tile(point["lat"], point["lon"])
    e, n, _ = to_utm(point["lat"], point["lon"])
    end = date.today()
    items = search(z, b, sq, end - timedelta(days=days), end, max_cloud=101)
    items.sort(key=lambda i: i["properties"]["eo:cloud_cover"])

    pw = build_channel_mask(items, e, n)
    if pw is None:
        if verbose:
            print(f"  {point['id']}: no channel mask, skipping")
        return []
    mask = pw["mask"]
    if verbose:
        print(f"  {point['id']}: tile T{z}{b}{sq}, {len(items)} scenes, "
              f"channel mask {int(mask.sum())} px from {pw['scenes_used']} scenes")

    by_date = sorted(items, key=lambda i: i["properties"]["datetime"])
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(lambda it: reading_for_scene(it, e, n, mask), by_date))

    rows = [r for r in rows if r]
    # one reading per date; keep the one with the most usable pixels
    best = {}
    for r in rows:
        if r["date"] not in best or r["water_pixel_count"] > best[r["date"]]["water_pixel_count"]:
            best[r["date"]] = r
    out = sorted(best.values(), key=lambda r: r["date"])
    if verbose:
        print(f"  {point['id']}: {len(out)} readings from {len(items)} scenes "
              f"({100*len(out)/max(len(items),1):.0f}% usable)")
    return out


FIELDS = ["date", "ndti", "ndti_std", "cloud_cover", "scene_id", "water_pixel_count"]


def write_csv(point_id, rows, outdir="data/readings"):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{point_id}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def main():
    os.environ.setdefault("GDAL_HTTP_CAINFO", "/root/.ccr/ca-bundle.crt")
    os.environ.setdefault("GDAL_DISABLE_READ_DIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
    for p in POINTS:
        rows = collect(p)
        if rows:
            print(f"  {p['id']}: wrote {write_csv(p['id'], rows)}  "
                  f"({rows[0]['date']} .. {rows[-1]['date']})\n")


if __name__ == "__main__":
    main()

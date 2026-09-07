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
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np

from .points import POINTS, mgrs_tile, to_utm
from .raster import grid_for, read_on_grid
from .search import search
from .water import SCL_CLOUDY, persistent_water

READING_RADIUS_M = 50.0
MASK_SCENES = 12
MIN_PIXELS = 3
# The Sentinel-2 L2A archive on AWS reaches back to 2017. Eighteen months of it
# yields only ~20 usable readings here, because the Pra basin is under cloud most
# of the time -- not enough to train an Isolation Forest on. We take the whole
# archive instead, which also gives the model several full wet/dry cycles so that
# seasonal turbidity is learned as normal rather than flagged as anomalous.
HISTORY_START = date(2017, 1, 1)


MASK_DIR = "data/masks"


def _mask_path(point_id):
    return os.path.join(MASK_DIR, f"{point_id}.npy")


def build_channel_mask(items, easting, northing, point_id=None, rebuild=False):
    """The channel mask, cached to disk.

    The mask must be *stable*: it defines which pixels every reading is measured
    over, so rebuilding it from whatever scenes a given run happens to see would
    make readings from different runs incomparable. It would also fail exactly
    when it matters -- a scheduled run looks back only ~30 days, and in the rainy
    season those scenes can all be too cloudy to derive a mask from, so the run
    would quietly collect nothing during the pollution season. Build it once from
    the clearest scenes in the archive, then reuse it.
    """
    if point_id and not rebuild and os.path.exists(_mask_path(point_id)):
        return {"mask": np.load(_mask_path(point_id)), "scenes_used": 0,
                "cached": True}

    pw = persistent_water(items[:MASK_SCENES], easting, northing,
                          half_m=READING_RADIUS_M)
    if pw is None or not pw["mask"].any():
        return None
    if point_id:
        os.makedirs(MASK_DIR, exist_ok=True)
        np.save(_mask_path(point_id), pw["mask"])
    return pw


def reading_for_scene(item, easting, northing, mask20):
    """One NDTI reading, or None when the scene is unusable here."""
    bounds = (easting - READING_RADIUS_M, northing - READING_RADIUS_M,
              easting + READING_RADIUS_M, northing + READING_RADIUS_M)
    # read everything, mask included, on one explicit 10 m grid
    h, w, _ = grid_for(bounds, 10.0)
    try:
        red = read_on_grid(item, "red", bounds, (h, w))
        green = read_on_grid(item, "green", bounds, (h, w))
        scl = read_on_grid(item, "scl", bounds, (h, w))
    except Exception:
        return None

    # the channel mask is on the 20 m grid covering the same bounds; both grids
    # are defined from those bounds, so this upsample is a clean 2x
    mh, mw = mask20.shape
    ry = np.clip((np.arange(h) * mh) // h, 0, mh - 1)
    rx = np.clip((np.arange(w) * mw) // w, 0, mw - 1)
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
    # The raw band medians are recorded alongside NDTI because NDTI normalises
    # away exactly the signal a heavy sediment load produces: at high turbidity
    # both bands brighten together and the ratio stops responding. See
    # TEST_RESULTS.md section 1 -- absolute red reflectance separated the one
    # documented pollution event that NDTI scored as entirely ordinary.
    return {
        "date": p["datetime"][:10],
        "ndti": round(float(np.median(vals)), 6),
        "ndti_std": round(float(np.std(vals)), 6),
        "red": round(float(np.median(red[usable])), 6),
        "green": round(float(np.median(green[usable])), 6),
        "cloud_cover": round(float(p.get("eo:cloud_cover", float("nan"))), 3),
        "scene_id": item["id"],
        "water_pixel_count": n,
    }


def collect(point, start=HISTORY_START, workers=16, verbose=True):
    z, b, sq = mgrs_tile(point["lat"], point["lon"])
    e, n, _ = to_utm(point["lat"], point["lon"])
    end = date.today()
    items = search(z, b, sq, start, end, max_cloud=101)
    items.sort(key=lambda i: i["properties"]["eo:cloud_cover"])

    pw = build_channel_mask(items, e, n, point_id=point["id"])
    if pw is None:
        if verbose:
            print(f"  {point['id']}: no channel mask, skipping")
        return []
    mask = pw["mask"]
    if verbose:
        src = "cached" if pw.get("cached") else f"{pw['scenes_used']} scenes"
        print(f"  {point['id']}: tile T{z}{b}{sq}, {len(items)} scenes, "
              f"channel mask {int(mask.sum())} px ({src})")

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


FIELDS = ["date", "ndti", "ndti_std", "red", "green",
          "cloud_cover", "scene_id", "water_pixel_count"]


def _clean(row):
    """Blank out missing values rather than writing the string 'nan'.

    Readings collected before `red`/`green` were added have no value for them.
    An empty cell reads as missing to both pandas and a human; the literal text
    "nan" reads as data until someone looks closely.
    """
    out = {}
    for k in FIELDS:
        v = row.get(k, "")
        if v is None or (isinstance(v, float) and v != v):
            v = ""
        out[k] = v
    return out


def write_csv(point_id, rows, outdir="data/readings"):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{point_id}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(_clean(r) for r in rows)
    return path


def main():
    os.environ.setdefault("GDAL_HTTP_CAINFO", "/root/.ccr/ca-bundle.crt")
    os.environ.setdefault("GDAL_DISABLE_READ_DIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
    start = HISTORY_START
    if len(sys.argv) > 1:
        start = date.fromisoformat(sys.argv[1])
    print(f"collecting from {start} to today\n")
    for p in POINTS:
        rows = collect(p, start=start)
        if rows:
            print(f"  {p['id']}: wrote {write_csv(p['id'], rows)}  "
                  f"({rows[0]['date']} .. {rows[-1]['date']})\n")


if __name__ == "__main__":
    main()

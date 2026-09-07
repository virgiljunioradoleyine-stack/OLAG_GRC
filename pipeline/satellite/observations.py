"""
Sentinel-2 observations for every monitoring station.

Batched by scene, not by station. Stations share tiles -- six of our eight sit
in T30NXL -- so opening each band once per scene and reading every station's
window from that open handle turns 8 x 1000 x 5 remote opens into 1000 x 5.
GDAL keeps the COG header cached per handle, so the per-station cost collapses
to a range request for a few kilobytes.

Bands read: red (B04), green (B03), nir (B08), swir16 (B11), scl.
Indices derived: NDTI, NDWI, MNDWI, red/green ratio.
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

from ..config import STATIONS, HISTORY_START
from ..io.atomic import atomic_write
from ..io.env import configure_gdal
from ..ndti import _band_scaling, _vsicurl
from ..points import mgrs_tile, to_utm
from ..raster import grid_for
from ..search import search
from ..water import SCL_CLOUDY, persistent_water
from .quality import quality_of

OBS_DIR = "data/observations"
MASK_DIR = "data/masks"
GRID_RES = 10.0
MASK_SCENES = 12
MIN_PIXELS = 3

BANDS = ("red", "green", "nir", "swir16", "scl")

OBS_FIELDS = [
    "date", "station_id", "scene_id",
    "ndti", "ndti_std", "ndwi", "mndwi", "red_green_ratio",
    "red", "green", "nir", "swir16",
    "water_pixel_count", "window_pixels", "cloud_fraction",
    "tile_cloud_cover", "quality", "quality_score",
]


# ------------------------------------------------------------------ masks ---

def mask_path(station_id):
    return os.path.join(MASK_DIR, f"{station_id}.npy")


def _own_channel(mask, transform, easting, northing):
    """Keep only the connected water body containing the station."""
    from scipy import ndimage
    lbl, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask
    rows, cols = np.nonzero(mask)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    k = int(np.argmin(np.hypot(xs - easting, ys - northing)))
    return lbl == lbl[rows[k], cols[k]]


def channel_mask(station, items, rebuild=False):
    """Stable channel mask for a station, cached to disk.

    Built once from the clearest scenes in the archive. It must not change
    between runs: it defines which pixels every reading is measured over, so a
    drifting mask would make readings from different runs incomparable.
    """
    p = mask_path(station.id)
    if not rebuild and os.path.exists(p):
        return np.load(p)
    e, n, _ = to_utm(station.lat, station.lon)
    pw = persistent_water(items[:MASK_SCENES], e, n, half_m=station.radius_m)
    if pw is None or not pw["mask"].any():
        return None
    m = _own_channel(pw["mask"], pw["transform"], e, n)
    if not m.any():
        return None
    os.makedirs(MASK_DIR, exist_ok=True)
    np.save(p, m)
    return m


# ------------------------------------------------------------- extraction ---

def _read_windows(ds, key, item, targets):
    """Read one open dataset at several station windows. Returns {id: array}."""
    scale, offset = _band_scaling(item, key)
    out = {}
    for sid, bounds, shape in targets:
        try:
            win = from_bounds(*bounds, transform=ds.transform)
            arr = ds.read(1, window=win, out_shape=shape, boundless=True,
                          fill_value=0).astype("float32")
            arr[arr == 0] = np.nan
            out[sid] = arr * scale + offset
        except Exception:
            out[sid] = None
    return out


def readings_for_scene(item, stations, masks):
    """Extract one observation per station from a single scene."""
    targets = []
    for s in stations:
        if masks.get(s.id) is None:
            continue
        e, n, _ = to_utm(s.lat, s.lon)
        b = (e - s.radius_m, n - s.radius_m, e + s.radius_m, n + s.radius_m)
        h, w, _ = grid_for(b, GRID_RES)
        targets.append((s.id, b, (h, w)))
    if not targets:
        return []

    bands = {}
    for key in BANDS:
        try:
            with rasterio.open(_vsicurl(item["assets"][key]["href"])) as ds:
                bands[key] = _read_windows(ds, key, item, targets)
        except Exception:
            return []          # a scene we cannot read is skipped, not guessed at

    props = item["properties"]
    obs_date = props["datetime"][:10]
    tile_cloud = props.get("eo:cloud_cover")

    rows = []
    for sid, _bounds, shape in targets:
        red = bands["red"].get(sid)
        green = bands["green"].get(sid)
        nir = bands["nir"].get(sid)
        swir = bands["swir16"].get(sid)
        scl = bands["scl"].get(sid)
        if any(a is None for a in (red, green, nir, swir, scl)):
            continue

        mask20 = masks[sid]
        h, w = shape
        mh, mw = mask20.shape
        ry = np.clip((np.arange(h) * mh) // h, 0, mh - 1)
        rx = np.clip((np.arange(w) * mw) // w, 0, mw - 1)
        channel = mask20[np.ix_(ry, rx)]

        scl_raw = np.nan_to_num(scl, nan=0).astype("uint8")
        cloudy = np.isin(scl_raw, list(SCL_CLOUDY))
        finite = np.isfinite(red) & np.isfinite(green) & np.isfinite(nir) & np.isfinite(swir)
        usable = channel & finite & ~cloudy

        n_px = int(usable.sum())
        n_channel = int(channel.sum())
        if n_px < MIN_PIXELS or n_channel == 0:
            continue

        cloud_frac = float((channel & cloudy).sum() / n_channel)

        r, g = red[usable], green[usable]
        ni, sw = nir[usable], swir[usable]

        def safe_nd(a, b):
            d = a + b
            ok = np.abs(d) > 1e-6
            return ((a - b) / np.where(ok, d, 1.0))[ok]

        ndti_vals = safe_nd(r, g)
        if ndti_vals.size < MIN_PIXELS:
            continue
        ndwi_vals = safe_nd(g, ni)
        mndwi_vals = safe_nd(g, sw)
        ratio = float(np.median(r) / np.median(g)) if np.median(g) != 0 else np.nan

        std = float(np.std(ndti_vals))
        level, score, _why = quality_of(n_px, std, cloud_frac)

        rows.append({
            "date": obs_date,
            "station_id": sid,
            "scene_id": item["id"],
            "ndti": round(float(np.median(ndti_vals)), 6),
            "ndti_std": round(std, 6),
            "ndwi": round(float(np.median(ndwi_vals)), 6) if ndwi_vals.size else "",
            "mndwi": round(float(np.median(mndwi_vals)), 6) if mndwi_vals.size else "",
            "red_green_ratio": round(ratio, 6) if ratio == ratio else "",
            "red": round(float(np.median(r)), 6),
            "green": round(float(np.median(g)), 6),
            "nir": round(float(np.median(ni)), 6),
            "swir16": round(float(np.median(sw)), 6),
            "water_pixel_count": n_px,
            "window_pixels": n_channel,
            "cloud_fraction": round(cloud_frac, 4),
            "tile_cloud_cover": round(float(tile_cloud), 3) if tile_cloud is not None else "",
            "quality": level,
            "quality_score": score,
        })
    return rows


# ------------------------------------------------------------- collection ---

def collect_tile(tile_key, stations, start, end=None, workers=16, verbose=True):
    """Collect observations for every station sharing one Sentinel-2 tile."""
    z, b, sq = tile_key
    end = end or date.today()
    items = search(z, b, sq, start, end, max_cloud=101)
    if not items:
        if verbose:
            print(f"  T{z}{b}{sq}: no scenes")
        return []
    items.sort(key=lambda i: i["properties"]["eo:cloud_cover"])

    masks = {}
    for s in stations:
        m = channel_mask(s, items)
        masks[s.id] = m
        if verbose:
            print(f"    {s.id} {s.name:24s} mask "
                  + (f"{int(m.sum())} px" if m is not None else "UNAVAILABLE"))

    usable_stations = [s for s in stations if masks.get(s.id) is not None]
    if not usable_stations:
        return []

    by_date = sorted(items, key=lambda i: i["properties"]["datetime"])
    if verbose:
        print(f"  T{z}{b}{sq}: {len(by_date)} scenes x {len(usable_stations)} stations")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        batches = list(ex.map(
            lambda it: readings_for_scene(it, usable_stations, masks), by_date))

    rows = [r for batch in batches for r in batch]
    if verbose:
        print(f"  T{z}{b}{sq}: {len(rows)} observations")
    return rows


def collect_all(start=HISTORY_START, end=None, stations=None, workers=16,
                verbose=True):
    """Collect for every station, grouped by tile so scenes are read once."""
    configure_gdal()
    stations = stations or STATIONS

    tiles = defaultdict(list)
    for s in stations:
        tiles[mgrs_tile(s.lat, s.lon)].append(s)

    start = date.fromisoformat(start) if isinstance(start, str) else start
    all_rows = []
    for tile_key, group in sorted(tiles.items(), key=lambda kv: str(kv[0])):
        all_rows += collect_tile(tile_key, group, start, end, workers, verbose)
    return all_rows


# ------------------------------------------------------------------- I/O ---

def write_observations(rows, path=None):
    """Write observations atomically, one row per station-date."""
    path = path or os.path.join(OBS_DIR, "observations.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    best = {}
    for r in rows:
        k = (r["station_id"], r["date"])
        if k not in best or r["water_pixel_count"] > best[k]["water_pixel_count"]:
            best[k] = r
    ordered = sorted(best.values(), key=lambda r: (r["station_id"], r["date"]))

    with atomic_write(path) as fh:
        w = csv.DictWriter(fh, fieldnames=OBS_FIELDS)
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") for k in OBS_FIELDS})
    return path, len(ordered)


def load_observations(path=None, station_id=None):
    path = path or os.path.join(OBS_DIR, "observations.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=OBS_FIELDS)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    for c in ("ndti", "ndti_std", "ndwi", "mndwi", "red_green_ratio",
              "red", "green", "nir", "swir16", "cloud_fraction",
              "tile_cloud_cover", "quality_score"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if station_id:
        df = df[df["station_id"] == station_id]
    return df.sort_values(["station_id", "date"]).reset_index(drop=True)


def main():
    import sys
    start = sys.argv[1] if len(sys.argv) > 1 else HISTORY_START
    print(f"collecting observations from {start}\n")
    rows = collect_all(start=start)
    path, n = write_observations(rows)
    print(f"\nwrote {path}: {n} observations")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())

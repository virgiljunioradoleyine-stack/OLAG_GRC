"""
Persistent-water mask from Sentinel-2.

Water is detected with MNDWI = (green - SWIR16) / (green + SWIR16) rather than
the SCL water class. SWIR is strongly absorbed by water no matter how much
sediment it carries, whereas SCL keys on the low reflectance of *clear* water
and misclassifies turbid water as bare soil -- see HICCUPS.md. Since turbidity
is the whole point of this project, SCL would have been blind to our signal.

A single scene is noisy, so water is judged across many clear dates: a pixel is
"persistent water" when it reads as water in most cloud-free observations.
"""
from __future__ import annotations

import numpy as np

from .raster import grid_for, read_on_grid

SCL_CLOUDY = {0, 1, 3, 8, 9, 10}   # nodata, saturated, shadow, cloud, cirrus
MIN_DENOM = 0.02                   # guard: BOA offset lets bands go negative
WATER_THRESHOLD = 0.0              # MNDWI > 0 => water


GRID_RES = 20.0   # metres; the native resolution of SWIR and SCL


def scene_water_mask(item, bounds):
    """(water, valid, transform) for one scene, on the shared 20 m grid."""
    h, w, tf = grid_for(bounds, GRID_RES)
    swir = read_on_grid(item, "swir16", bounds, (h, w))
    green = read_on_grid(item, "green", bounds, (h, w))
    scl = read_on_grid(item, "scl", bounds, (h, w))
    scl_raw = np.nan_to_num(scl, nan=0).astype("uint8")

    denom = green + swir
    valid = (np.isfinite(green) & np.isfinite(swir) & (denom > MIN_DENOM)
             & ~np.isin(scl_raw, list(SCL_CLOUDY)))
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = np.where(valid, (green - swir) / np.where(valid, denom, 1.0), np.nan)
    return valid & (mndwi > WATER_THRESHOLD), valid, tf


def persistent_water(items, easting, northing, half_m=1000.0, min_fraction=0.6):
    """Combine several scenes into a persistent-water mask around a point.

    Returns dict with the boolean mask, the per-pixel water frequency, the
    number of clear observations per pixel, and the raster transform.
    """
    bounds = (easting - half_m, northing - half_m,
              easting + half_m, northing + half_m)

    water_sum = valid_sum = None
    transform = None
    used = 0
    for it in items:
        try:
            water, valid, tf = scene_water_mask(it, bounds)
        except Exception:
            continue
        if water_sum is None:
            water_sum = np.zeros(water.shape, "int32")
            valid_sum = np.zeros(water.shape, "int32")
            transform = tf
        elif water.shape != water_sum.shape:
            continue
        water_sum += water.astype("int32")
        valid_sum += valid.astype("int32")
        used += 1

    if water_sum is None:
        return None

    with np.errstate(invalid="ignore", divide="ignore"):
        freq = np.where(valid_sum > 0, water_sum / np.maximum(valid_sum, 1), np.nan)
    return {
        "mask": (valid_sum >= 2) & (freq >= min_fraction),
        "frequency": freq,
        "observations": valid_sum,
        "transform": transform,
        "scenes_used": used,
    }


def snap_to_channel(pw, easting, northing, radius_m=50.0, max_move_m=400.0):
    """Find the best nearby reading location on the water mask.

    Snapping to the single *nearest* water pixel lands on whatever bend or
    sliver happens to be closest, which often yields a 1-pixel window. Instead
    score every candidate centre by how many persistent-water pixels fall inside
    its reading window, then among the good ones take the closest to the
    original. That favours a wide, straight reach over a nearby thread of water.

    Returns (easting, northing, pixel_count) or None.
    """
    mask, tf = pw["mask"], pw["transform"]
    if not mask.any():
        return None

    px = abs(tf.a)                      # metres per mask pixel
    rad = int(np.ceil(radius_m / px))
    offs = [(dy, dx) for dy in range(-rad, rad + 1) for dx in range(-rad, rad + 1)
            if np.hypot(dy * px, dx * px) <= radius_m]

    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    best = None
    for r, c in zip(ys, xs):
        cnt = 0
        for dy, dx in offs:
            rr, cc = r + dy, c + dx
            if 0 <= rr < h and 0 <= cc < w and mask[rr, cc]:
                cnt += 1
        ex = tf.c + (c + 0.5) * tf.a
        ny = tf.f + (r + 0.5) * tf.e
        dist = float(np.hypot(ex - easting, ny - northing))
        if dist > max_move_m:
            continue
        # maximise pixels, then minimise how far we move
        key = (-cnt, dist)
        if best is None or key < best[0]:
            best = (key, ex, ny, cnt)
    if best is None:
        return None
    return best[1], best[2], best[3]

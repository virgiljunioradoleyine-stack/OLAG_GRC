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
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

from .ndti import _band_scaling, _vsicurl

SCL_CLOUDY = {0, 1, 3, 8, 9, 10}   # nodata, saturated, shadow, cloud, cirrus
MIN_DENOM = 0.02                   # guard: BOA offset lets bands go negative
WATER_THRESHOLD = 0.0              # MNDWI > 0 => water


def _read(item, key, bounds, out_shape=None):
    scale, offset = _band_scaling(item, key)
    with rasterio.open(_vsicurl(item["assets"][key]["href"])) as ds:
        win = from_bounds(*bounds, transform=ds.transform).round_offsets().round_lengths()
        kw = {"out_shape": out_shape, "resampling": Resampling.nearest} if out_shape else {}
        arr = ds.read(1, window=win, **kw).astype("float32")
        arr[arr == 0] = np.nan
        tf = ds.window_transform(win) if out_shape is None else None
        return arr * scale + offset, tf


def scene_water_mask(item, bounds):
    """(water, valid, transform) for one scene on the 20 m SWIR grid."""
    swir, tf = _read(item, "swir16", bounds)
    green, _ = _read(item, "green", bounds, out_shape=swir.shape)
    scl, _ = _read(item, "scl", bounds, out_shape=swir.shape)
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

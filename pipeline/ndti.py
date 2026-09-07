"""
NDTI (Normalized Difference Turbidity Index) from Sentinel-2 L2A COGs.

    NDTI = (red - green) / (red + green)

Reads only a small window around a monitoring point via HTTP range requests --
the full scene is never downloaded. Water pixels are selected with the Scene
Classification Layer (SCL class 6 = water); cloud/shadow classes are excluded.
"""
from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

# Sentinel-2 SCL classes
SCL_WATER = 6
SCL_BAD = {0, 1, 3, 8, 9, 10}  # nodata, saturated, shadow, cloud med/high, cirrus

DEFAULT_RADIUS_M = 50.0


def _vsicurl(href: str) -> str:
    return href if href.startswith("/vsicurl/") else "/vsicurl/" + href


def _band_scaling(item, key):
    """Return (scale, offset) for an asset, from the scene's own STAC metadata.

    Sentinel-2 processing baseline >= 04.00 introduced a BOA reflectance offset,
    and the item's `raster:bands` advertises it as `offset: -0.1`. But Earth
    Search's COGs have usually already had it applied, flagged by the scene
    property `earthsearch:boa_offset_applied`. Applying it a second time shifts
    every band down by 0.1 and drives dark surfaces -- water especially --
    negative, which silently inverts normalized-difference indices. So honour
    the flag: when the offset is already in the pixels, do not reapply it.
    """
    rb = (item["assets"][key].get("raster:bands") or [{}])[0]
    scale = float(rb.get("scale", 1.0))
    offset = float(rb.get("offset", 0.0))
    if item.get("properties", {}).get("earthsearch:boa_offset_applied"):
        offset = 0.0
    return scale, offset


def read_point_window(item, easting, northing, radius_m=DEFAULT_RADIUS_M):
    """Read red/green/SCL over a square window centred on a UTM coordinate.

    Returns dict with reflectance arrays (scale+offset applied), the SCL array
    resampled to the 10 m grid, and pixel counts.
    """
    bounds = (easting - radius_m, northing - radius_m,
              easting + radius_m, northing + radius_m)

    out = {}
    for key in ("red", "green"):
        scale, offset = _band_scaling(item, key)
        with rasterio.open(_vsicurl(item["assets"][key]["href"])) as ds:
            win = from_bounds(*bounds, transform=ds.transform).round_offsets().round_lengths()
            arr = ds.read(1, window=win).astype("float32")
            arr[arr == (ds.nodata or 0)] = np.nan
            out[key] = arr * scale + offset
        out.setdefault("shape", out[key].shape)

    shape = out["red"].shape
    with rasterio.open(_vsicurl(item["assets"]["scl"]["href"])) as ds:
        win = from_bounds(*bounds, transform=ds.transform).round_offsets().round_lengths()
        out["scl"] = ds.read(1, window=win, out_shape=shape,
                             resampling=Resampling.nearest)

    return out


def ndti_at_point(item, easting, northing, radius_m=DEFAULT_RADIUS_M,
                  min_water_pixels=3):
    """Compute a single NDTI reading at a point.

    Returns dict(ndti, water_pixel_count, valid, reason) -- ndti is None when
    the point has too few usable water pixels in this scene.
    """
    w = read_point_window(item, easting, northing, radius_m)
    red, green, scl = w["red"], w["green"], w["scl"]

    water = (scl == SCL_WATER)
    bad = np.isin(scl, list(SCL_BAD))
    denom = red + green
    usable = water & ~bad & np.isfinite(red) & np.isfinite(green) & (np.abs(denom) > 1e-6)

    n = int(usable.sum())
    result = {
        "water_pixel_count": n,
        "window_pixels": int(scl.size),
        "cloud_pixels_in_window": int(bad.sum()),
    }
    if n < min_water_pixels:
        result.update(ndti=None, valid=False,
                      reason=f"only {n} usable water pixels (need >= {min_water_pixels})")
        return result

    vals = ((red - green) / denom)[usable]
    result.update(
        ndti=float(np.median(vals)),      # median: robust to a stray mixed pixel
        ndti_mean=float(np.mean(vals)),
        ndti_std=float(np.std(vals)),
        valid=True,
        reason="ok",
    )
    return result

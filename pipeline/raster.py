"""
Reading bands onto one common grid.

Sentinel-2 bands come at different resolutions (10 m for red/green, 20 m for
SWIR and SCL), so they must be resampled onto a shared grid before they can be
combined pixel-by-pixel. The obvious way -- read one band, then read the others
with `out_shape` set to the first band's shape -- is wrong near a tile edge:
rasterio clips a window that runs past the raster, each band clips by a
different number of its own pixels, and forcing them to a common shape then
stretches misaligned data over each other. No error is raised; the arrays just
quietly stop describing the same ground.

That bug is invisible in the middle of a tile and produces confidently wrong
answers at the edge, so instead we define the target grid ourselves from the
requested bounds and read every band onto it with a boundless read. Areas
outside the raster come back as nodata rather than shifting the grid.
"""
from __future__ import annotations

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.windows import from_bounds


def grid_for(bounds, res):
    """(height, width, transform) for a target grid covering `bounds`."""
    minx, miny, maxx, maxy = bounds
    w = max(1, int(round((maxx - minx) / res)))
    h = max(1, int(round((maxy - miny) / res)))
    return h, w, Affine(res, 0.0, minx, 0.0, -res, maxy)


def read_on_grid(item, key, bounds, shape, resampling=Resampling.nearest):
    """Read one asset onto an explicit grid. Returns float32 with NaN nodata."""
    scale, offset = _band_scaling(item, key)
    with rasterio.open(_vsicurl(item["assets"][key]["href"])) as ds:
        win = from_bounds(*bounds, transform=ds.transform)
        arr = ds.read(
            1, window=win, out_shape=shape, boundless=True,
            fill_value=0, resampling=resampling,
        ).astype("float32")
    arr[arr == 0] = np.nan
    return arr * scale + offset

# ---------------------------------------------------------------- scaling ---

def _vsicurl(href: str) -> str:
    return href if href.startswith("/vsicurl/") else "/vsicurl/" + href


def _band_scaling(item, key):
    """Return (scale, offset) for an asset, from the scene's own STAC metadata.

    Sentinel-2 processing baseline >= 04.00 introduced a BOA reflectance offset,
    advertised as `offset: -0.1` in `raster:bands`. Earth Search's COGs have
    usually already had it applied, flagged by the scene property
    `earthsearch:boa_offset_applied`. Applying it a second time shifts every band
    down by 0.1 and drives dark surfaces -- water especially -- negative, which
    silently inverts normalised-difference indices. So honour the flag: when the
    offset is already in the pixels, do not reapply it.
    """
    rb = (item["assets"][key].get("raster:bands") or [{}])[0]
    scale = float(rb.get("scale", 1.0))
    offset = float(rb.get("offset", 0.0))
    if item.get("properties", {}).get("earthsearch:boa_offset_applied"):
        offset = 0.0
    return scale, offset

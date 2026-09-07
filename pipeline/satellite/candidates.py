"""
Candidate monitoring sites along the Pra.

Powers click-to-add on the dashboard map. A click cannot verify anything by
itself -- checking whether a point sits on water needs the satellite pipeline --
so the verification is done here, offline, and the dashboard snaps a click to
the nearest already-verified candidate. What the user sees is therefore a real
measurement, not a guess made in the browser.

Candidates are walked along the chain of existing stations, which are known to
be on the channel, and each is snapped onto the persistent-water mask and scored
by how many water pixels a reading there would actually get.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date

import numpy as np

from ..config import STATIONS, HISTORY_START
from ..io.atomic import write_json
from ..io.env import configure_gdal
from ..points import from_utm, mgrs_tile, to_utm
from ..search import search
from ..water import persistent_water, snap_to_channel

OUT_PATH = os.path.join("web", "public", "data", "candidates.geojson")

SPACING_M = 1500.0          # how far apart to walk along the river
SEARCH_RADIUS_M = 900.0     # how far a candidate may be snapped
READING_RADIUS_M = 500.0    # matches Station.radius_m
MASK_SCENES = 12
MIN_PIXELS = 60             # below this a station would be too noisy to add
DEDUPE_M = 700.0            # candidates closer together than this are the same


def _interpolate(a, b, spacing_m):
    """Points every `spacing_m` along the straight line from a to b (UTM)."""
    ax, ay, _ = to_utm(a.lat, a.lon)
    bx, by, _ = to_utm(b.lat, b.lon)
    dist = float(np.hypot(bx - ax, by - ay))
    n = max(int(dist // spacing_m), 1)
    return [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(1, n)]


def build_candidates(stations=None, spacing_m=SPACING_M, verbose=True):
    configure_gdal()
    stations = sorted(stations or STATIONS, key=lambda s: s.order)

    scenes_by_tile = {}
    def scenes_for(tile):
        if tile not in scenes_by_tile:
            z, b, sq = tile
            items = search(z, b, sq, date.fromisoformat(HISTORY_START), date.today(),
                           max_cloud=101)
            items.sort(key=lambda i: i["properties"]["eo:cloud_cover"])
            scenes_by_tile[tile] = items[:MASK_SCENES]
        return scenes_by_tile[tile]

    seeds = []
    for i in range(1, len(stations)):
        seeds += _interpolate(stations[i - 1], stations[i], spacing_m)
    if verbose:
        print(f"walking {len(seeds)} seed points along the station chain")

    existing = [to_utm(s.lat, s.lon)[:2] for s in stations]
    found, skipped = [], 0

    for k, (ex, ny) in enumerate(seeds, 1):
        lat, lon = from_utm(ex, ny, 32630)
        tile = mgrs_tile(lat, lon)
        try:
            pw = persistent_water(scenes_for(tile), ex, ny,
                                  half_m=SEARCH_RADIUS_M + READING_RADIUS_M)
        except Exception:
            skipped += 1
            continue
        if pw is None or not pw["mask"].any():
            skipped += 1
            continue

        snap = snap_to_channel(pw, ex, ny, radius_m=READING_RADIUS_M,
                               max_move_m=SEARCH_RADIUS_M)
        if not snap:
            skipped += 1
            continue
        sx, sy, px = snap
        if px < MIN_PIXELS:
            skipped += 1
            continue

        # do not offer a candidate that duplicates a station or another candidate
        too_close = any(np.hypot(sx - x, sy - y) < DEDUPE_M for x, y in existing)
        if too_close:
            skipped += 1
            continue
        existing.append((sx, sy))

        clat, clon = from_utm(sx, sy, 32630)
        z, b, sq = tile
        found.append({
            "lat": round(clat, 6), "lon": round(clon, 6),
            "water_pixels": int(px),
            "tile": f"T{z}{b}{sq}",
            "moved_m": round(float(np.hypot(sx - ex, sy - ny))),
        })
        if verbose and k % 10 == 0:
            print(f"  {k}/{len(seeds)} seeds — {len(found)} candidates so far")

    if verbose:
        print(f"\n{len(found)} candidates, {skipped} seeds rejected "
              f"(no channel, too few pixels, or duplicate)")
    return found


def write_candidates(candidates, path=OUT_PATH):
    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "purpose": "Verified candidate sites for click-to-add on the map",
            "min_water_pixels": MIN_PIXELS,
            "reading_radius_m": READING_RADIUS_M,
            "note": ("Each candidate was snapped onto a persistent-water mask "
                     "built from the clearest scenes and scored by the water "
                     "pixels a reading there would actually get. A click on the "
                     "map snaps to the nearest of these, so what is shown is a "
                     "measured value, not a browser-side guess."),
        },
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
             "properties": {k: v for k, v in c.items() if k not in ("lat", "lon")}}
            for c in candidates
        ],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_json(path, fc)
    return path


def main():
    cands = build_candidates()
    if not cands:
        print("no candidates found — leaving the existing file untouched")
        return 1
    print(f"\nwrote {write_candidates(cands)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Add a monitoring station from a verified candidate site.

Run by the add-station workflow when someone clicks a point on the Live Map.
The request arrives from a public issue, so nothing in it is trusted: the only
coordinates this will accept are ones the pipeline itself already measured and
published in `candidates.geojson`. A request naming any other point is refused.
That is what makes the button safe to expose without a token or a login -- the
worst a stranger can do is add a station the satellite record already says is
usable river.

Usage:
    python -m scripts.add_station --lat 5.853077 --lon -1.539747 [--name "..."]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from pipeline.config import (
    ADDED_PATH, FOUNDING_STATIONS, _haversine_m, build_network,
    load_added_stations,
)

CANDIDATES_PATH = "web/public/data/candidates.geojson"
MATCH_TOLERANCE_M = 60.0     # a click snaps to a candidate before it is sent
MIN_SEPARATION_M = 400.0     # do not sit on top of an existing station


class Refused(Exception):
    """The request cannot be honoured. The message is shown to the requester."""


def _load_candidates(path=CANDIDATES_PATH):
    if not os.path.exists(path):
        raise Refused(
            "No candidate sites are published yet, so no point can be verified. "
            "The pipeline generates them; wait for a run to finish and try again.")
    with open(path) as fh:
        return json.load(fh).get("features", [])


def match_candidate(lat, lon, candidates, tolerance_m=MATCH_TOLERANCE_M):
    """The published candidate this request refers to, or refuse."""
    best, best_d = None, None
    for f in candidates:
        lon_c, lat_c = f["geometry"]["coordinates"][:2]
        d = _haversine_m(lat, lon, lat_c, lon_c)
        if best_d is None or d < best_d:
            best, best_d = f, d
    if best is None or best_d > tolerance_m:
        raise Refused(
            f"({lat:.6f}, {lon:.6f}) is not a verified candidate site — the "
            f"nearest one is {best_d:,.0f} m away. Only points the pipeline has "
            f"already checked against the satellite water mask can be added, so "
            f"pick a site on the map rather than typing coordinates.")
    return best, best_d


def next_station_id(stations):
    used = set()
    for s in stations:
        m = re.fullmatch(r"P(\d+)", s.id)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"P{n:02d}"


def add_station(lat, lon, name=None, role="monitor", path=ADDED_PATH,
                candidates_path=CANDIDATES_PATH):
    """Validate a request and append it. Returns the new station's record."""
    candidates = _load_candidates(candidates_path)
    feat, moved = match_candidate(lat, lon, candidates)
    lon_c, lat_c = feat["geometry"]["coordinates"][:2]
    props = feat.get("properties", {})

    existing = build_network(added=load_added_stations(path))
    for s in existing:
        d = _haversine_m(lat_c, lon_c, s.lat, s.lon)
        if d < MIN_SEPARATION_M:
            raise Refused(
                f"That site is only {d:,.0f} m from {s.id} ({s.name}). Stations "
                f"closer than {MIN_SEPARATION_M:.0f} m measure the same water, "
                f"so it would add readings without adding information.")

    sid = next_station_id(existing)
    record = {
        "id": sid,
        "name": name or f"Pra Reach {sid}",
        "lat": round(float(lat_c), 6),
        "lon": round(float(lon_c), 6),
        "role": role,
        "description": (
            f"Added from the Live Map. The persistent-water mask gives "
            f"{props.get('water_pixels', '?')} usable water pixels here, in "
            f"Sentinel-2 tile {props.get('tile', '?')}."),
        "radius_m": 500.0,
        "source": {
            "method": "map_click",
            "water_pixels": props.get("water_pixels"),
            "tile": props.get("tile"),
            "snapped_m": round(float(moved), 1),
        },
    }

    added = load_added_stations(path)
    added.append(record)
    doc = {"stations": added}
    if os.path.exists(path):
        with open(path) as fh:
            prev = json.load(fh)
        if isinstance(prev, dict) and "note" in prev:
            doc = {"note": prev["note"], "stations": added}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")

    chain = build_network(added=added)
    record["order"] = next(s.order for s in chain if s.id == sid)
    record["network_size"] = len(chain)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--name")
    ap.add_argument("--role", default="monitor",
                    choices=["monitor", "control", "intake", "downstream"])
    a = ap.parse_args(argv)
    try:
        rec = add_station(a.lat, a.lon, a.name, a.role)
    except Refused as ex:
        print(f"REFUSED: {ex}", file=sys.stderr)
        return 2
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

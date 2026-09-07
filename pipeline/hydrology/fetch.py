"""Entry point for acquiring river geometry and place names."""
from __future__ import annotations

import sys

from ..config import STATIONS
from .network import build_network
from .overpass import OverpassUnavailable, fetch_nearby_places, fetch_river_geometry


def main():
    force = "--force" in sys.argv
    status = 0
    try:
        fc = fetch_river_geometry(force=force)
        print(f"river geometry: {len(fc['features'])} segments "
              f"({fc['metadata']['license']})")
    except OverpassUnavailable as ex:
        print(f"river geometry UNAVAILABLE: {ex}")
        fc, status = None, 1

    try:
        places = fetch_nearby_places(STATIONS, force=force)
        named = sum(1 for v in places["places"].values() if v["nearest_place"])
        print(f"place names: {named}/{len(STATIONS)} stations matched")
        for sid, v in places["places"].items():
            if v["nearest_place"]:
                print(f"  {sid}: {v['nearest_place']} ({v['place_type']}, "
                      f"{v['distance_m']} m)")
    except OverpassUnavailable as ex:
        print(f"place names UNAVAILABLE: {ex}")
        status = 1

    net = build_network(STATIONS, fc)
    print(f"\nnetwork: {net['method']}")
    for s in net["segments"]:
        print(f"  {s['from']} -> {s['to']}  {s['distance_m']/1000:6.1f} km river "
              f"({s['straight_line_m']/1000:.1f} km straight)  "
              f"travel {s['travel_hours_min']}-{s['travel_hours_max']} h")
    return status


if __name__ == "__main__":
    raise SystemExit(main())

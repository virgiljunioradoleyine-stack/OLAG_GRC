"""
River network relationships between monitoring stations.

Turns the OSM centreline into the thing the features actually need: how far
apart two stations are *along the river*, not as the crow flies. On a meandering
river those differ substantially, and it is the along-channel distance that sets
how long water takes to travel between stations.

Travel time is reported as a range rather than a single number. River velocity
varies with discharge and season, and we have no gauge data; quoting one figure
would imply a precision we do not have.
"""
from __future__ import annotations

import os
from math import asin, cos, radians, sin, sqrt

from ..io.atomic import read_json, write_json
from .overpass import RIVER_PATH, load_river

NETWORK_PATH = os.path.join("data", "hydrology", "network.json")

# Plausible mean velocity range for a lowland West African river.
# Used only to express lead time as a range; never as a precise prediction.
VELOCITY_MS_LOW = 0.3
VELOCITY_MS_HIGH = 1.0


def haversine_m(a_lat, a_lon, b_lat, b_lon):
    dlat, dlon = radians(b_lat - a_lat), radians(b_lon - a_lon)
    h = (sin(dlat / 2) ** 2
         + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(dlon / 2) ** 2)
    return 2 * 6371000.0 * asin(sqrt(h))


def _all_vertices(fc):
    pts = []
    for f in (fc or {}).get("features", []):
        for lon, lat in f["geometry"]["coordinates"]:
            pts.append((lat, lon))
    return pts


def _snap_index(pts, lat, lon):
    best, best_d = None, None
    for i, (p_lat, p_lon) in enumerate(pts):
        d = haversine_m(lat, lon, p_lat, p_lon)
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best, best_d


def build_network(stations, fc=None):
    """Along-river distances and travel-time ranges between adjacent stations.

    Falls back to straight-line distance when the OSM geometry is unavailable,
    and says so in the output rather than silently substituting.
    """
    fc = fc if fc is not None else load_river()
    pts = _all_vertices(fc)

    ordered = sorted(stations, key=lambda s: s.order)
    nodes, method = {}, "osm_centreline"

    if pts:
        # cumulative distance along the concatenated centreline
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + haversine_m(*pts[i - 1], *pts[i]))
        for s in ordered:
            idx, snap_d = _snap_index(pts, s.lat, s.lon)
            nodes[s.id] = {"river_m": cum[idx], "snap_distance_m": round(snap_d)}
        # a bad snap means the centreline does not really cover our stations
        if max(n["snap_distance_m"] for n in nodes.values()) > 2000:
            method = "straight_line_fallback"
    else:
        method = "straight_line_fallback"

    if method == "straight_line_fallback":
        nodes, run = {}, 0.0
        for i, s in enumerate(ordered):
            if i:
                run += haversine_m(ordered[i - 1].lat, ordered[i - 1].lon,
                                   s.lat, s.lon)
            nodes[s.id] = {"river_m": run, "snap_distance_m": None}

    segments = []
    for i in range(1, len(ordered)):
        up, dn = ordered[i - 1], ordered[i]
        d = abs(nodes[dn.id]["river_m"] - nodes[up.id]["river_m"])
        segments.append({
            "from": up.id, "to": dn.id,
            "distance_m": round(d),
            "straight_line_m": round(haversine_m(up.lat, up.lon, dn.lat, dn.lon)),
            "travel_hours_min": round(d / VELOCITY_MS_HIGH / 3600, 1) if d else 0.0,
            "travel_hours_max": round(d / VELOCITY_MS_LOW / 3600, 1) if d else 0.0,
        })

    net = {
        "method": method,
        "note": ("Distances measured along the OSM river centreline."
                 if method == "osm_centreline" else
                 "OSM centreline unavailable or did not cover the stations; "
                 "distances are straight-line and therefore UNDERESTIMATE the "
                 "true along-river distance."),
        "velocity_range_ms": [VELOCITY_MS_LOW, VELOCITY_MS_HIGH],
        "stations": {k: {"river_km": round(v["river_m"] / 1000, 2),
                         "snap_distance_m": v["snap_distance_m"]}
                     for k, v in nodes.items()},
        "segments": segments,
    }
    write_json(NETWORK_PATH, net)
    return net


def load_network():
    return read_json(NETWORK_PATH)


def river_distances(stations):
    """{station_id: river_km}, building the network if it is not cached."""
    net = load_network()
    if not net:
        net = build_network(stations)
    return {k: v["river_km"] for k, v in net["stations"].items()}

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

# Plausible bounds on channel sinuosity (river length / straight-line length).
# Used to detect when the OSM centreline walk has produced nonsense.
MIN_SINUOSITY = 0.95   # slightly below 1 to tolerate floating-point error
MAX_SINUOSITY = 3.0
TYPICAL_SINUOSITY = 1.4


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


def build_network(stations, fc=None, path=NETWORK_PATH):
    """Along-river distances and travel-time ranges between adjacent stations.

    Falls back to straight-line distance when the OSM geometry is unavailable,
    and says so in the output rather than silently substituting.

    `path=None` computes without persisting. Tests must pass it: this function
    used to write the production network file unconditionally, so running the
    suite -- including a test that feeds it deliberately disjoint fake geometry
    -- overwrote the real published distances with test output.
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
        straight = haversine_m(up.lat, up.lon, dn.lat, dn.lon)
        d = abs(nodes[dn.id]["river_m"] - nodes[up.id]["river_m"])

        # Sanity-check the along-river distance against the straight line.
        #
        # Overpass returns the river as many DISJOINT ways in arbitrary order.
        # Walking a naive cumulative distance over their concatenated vertices
        # therefore jumps between segments that are not connected, and the first
        # CI run produced 323 km of river for a 32 km straight line. Real rivers
        # meander, but sinuosity is bounded: roughly 1.0-3.0 for a channel like
        # the Pra. Anything outside that says the centreline walk is unreliable
        # for this pair, so we fall back to the straight line and label the
        # segment rather than publishing a fabricated distance.
        sinuosity = (d / straight) if straight > 0 else 0.0
        seg_method = "osm_centreline"
        if not (MIN_SINUOSITY <= sinuosity <= MAX_SINUOSITY):
            d = straight * TYPICAL_SINUOSITY
            seg_method = "straight_line_estimate"

        segments.append({
            "from": up.id, "to": dn.id,
            "distance_m": round(d),
            "straight_line_m": round(straight),
            "sinuosity": round(sinuosity, 2) if straight > 0 else None,
            "method": seg_method,
            "travel_hours_min": round(d / VELOCITY_MS_HIGH / 3600, 1) if d else 0.0,
            "travel_hours_max": round(d / VELOCITY_MS_LOW / 3600, 1) if d else 0.0,
        })

    n_fallback = sum(1 for s in segments if s["method"] != "osm_centreline")
    if n_fallback:
        method = ("mixed" if n_fallback < len(segments)
                  else "straight_line_fallback")

    net = {
        "method": method,
        "segments_from_centreline": len(segments) - n_fallback,
        "segments_estimated": n_fallback,
        "note": (
            "Distances measured along the OSM river centreline."
            if method == "osm_centreline" else
            f"{n_fallback} of {len(segments)} segments could not be measured "
            f"reliably along the OSM centreline -- Overpass returns the river as "
            f"disjoint ways, so a cumulative walk can jump between unconnected "
            f"pieces. Those segments use straight-line distance scaled by a "
            f"typical sinuosity of {TYPICAL_SINUOSITY}, and are marked "
            f"method='straight_line_estimate'. Treat them as approximate."),
        "velocity_range_ms": [VELOCITY_MS_LOW, VELOCITY_MS_HIGH],
        "stations": _chainage(ordered, segments, nodes),
        "segments": segments,
    }
    if path:
        write_json(path, net)
    return net


def _chainage(ordered, segments, nodes):
    """Distance downstream from the first station, accumulated from segments.

    Not read off the centreline walk. That walk is the thing the sinuosity
    check exists to distrust -- it jumps between disjoint Overpass ways -- and
    taking chainage straight from it published a river that ran 277 km at P01,
    10 km at P02 and 334 km at P03, which is not an ordering any river has.
    The segment distances are already validated, so accumulating those gives a
    chainage that is monotonic downstream and consistent with the distances
    published beside it.
    """
    by_pair = {(s["from"], s["to"]): s["distance_m"] for s in segments}
    out, run = {}, 0.0
    for i, s in enumerate(ordered):
        if i:
            run += by_pair[(ordered[i - 1].id, s.id)]
        out[s.id] = {"river_km": round(run / 1000, 2),
                     "snap_distance_m": nodes[s.id]["snap_distance_m"]}
    return out


def load_network():
    return read_json(NETWORK_PATH)


def river_distances(stations):
    """{station_id: river_km}, building the network if it is not cached."""
    net = load_network()
    if not net:
        net = build_network(stations)
    return {k: v["river_km"] for k, v in net["stations"].items()}

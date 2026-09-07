"""River-network tests. The distance sanity check exists because CI caught a
real failure: Overpass returns the Pra as disjoint ways, and a naive cumulative
walk over their concatenated vertices produced 323 km of river for a 32 km
straight line."""
import pytest

from pipeline.config import STATIONS
from pipeline.hydrology.network import (
    MAX_SINUOSITY, MIN_SINUOSITY, TYPICAL_SINUOSITY, build_network, haversine_m,
)


def test_haversine_is_sane():
    # Accra to Kumasi is roughly 200 km
    d = haversine_m(5.6037, -0.1870, 6.6885, -1.6244) / 1000
    assert 180 < d < 220


def test_network_covers_every_adjacent_pair():
    net = build_network(STATIONS, fc=None)
    assert len(net["segments"]) == len(STATIONS) - 1
    for s in net["segments"]:
        assert s["distance_m"] > 0
        assert s["travel_hours_min"] <= s["travel_hours_max"]


def test_implausible_river_distance_is_rejected():
    """A disjoint-way artifact must never be published as a real distance."""
    net = build_network(STATIONS, fc=None)
    for s in net["segments"]:
        ratio = s["distance_m"] / max(s["straight_line_m"], 1)
        assert ratio <= MAX_SINUOSITY + 0.01, (
            f"{s['from']}->{s['to']} reports {ratio:.1f}x its straight-line "
            f"distance, which is not a real river")


def test_fallback_segments_are_labelled():
    net = build_network(STATIONS, fc=None)
    for s in net["segments"]:
        assert s["method"] in ("osm_centreline", "straight_line_estimate")
    assert net["segments_from_centreline"] + net["segments_estimated"] == len(net["segments"])


def test_disjoint_geometry_triggers_the_fallback():
    """Simulate Overpass returning two unconnected river pieces."""
    fc = {"features": [
        {"geometry": {"type": "LineString",
                      "coordinates": [[-1.52, 5.88], [-1.53, 5.87]]}},
        # a piece 200 km away, as an unordered second way
        {"geometry": {"type": "LineString",
                      "coordinates": [[-3.00, 7.50], [-3.01, 7.49]]}},
    ]}
    net = build_network(STATIONS, fc=fc)
    for s in net["segments"]:
        ratio = s["distance_m"] / max(s["straight_line_m"], 1)
        assert ratio <= MAX_SINUOSITY + 0.01

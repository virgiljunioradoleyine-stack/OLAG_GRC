"""
Pra River Watch — monitoring network and system configuration.

The network is data-driven: adding, removing or reordering stations requires no
code change anywhere else. Stations are ordered upstream → downstream, which is
what makes the upstream/downstream feature logic and the map's river ordering
work for an arbitrary number of stations rather than a hard-coded three.

Every coordinate here was verified against Sentinel-2 persistent-water masks
before being added -- see `scripts/verify_point.py` and COORDINATES_GUIDE.md.
The coordinates in the original project brief were all off-channel.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict


@dataclass
class Station:
    id: str                     # stable short code, e.g. "P01"
    name: str                   # human label
    lat: float
    lon: float
    role: str                   # control | monitor | intake | downstream
    order: int                  # 1 = furthest upstream
    description: str = ""
    place_source: str = "provisional"   # set to "osm" once resolved from OSM
    radius_m: float = 500.0     # reading window radius; ~1 km of channel

    @property
    def upstream_of(self):
        return [s.id for s in STATIONS if s.order > self.order]

    @property
    def downstream_of(self):
        return [s.id for s in STATIONS if s.order < self.order]

    def to_dict(self):
        d = asdict(self)
        d["upstream_of"] = self.upstream_of
        d["downstream_of"] = self.downstream_of
        return d


# The founding network, ordered upstream to downstream. The Pra flows roughly
# north to south, reaching the sea near Shama at about 5.01 N.
#
# `order` here is the seed chain. It is recomputed for the whole network once
# stations added from the map are merged in, so a station inserted midstream
# renumbers everything below it instead of being pinned to the end.
FOUNDING_STATIONS = [
    Station("P01", "Pra Upper Basin", 5.875062, -1.522239, "control", 1,
            "Reference station on the Pra mainstem above the Pra/Offin "
            "confluence. The Offin is the heavily mined tributary, so this "
            "station is not exposed to Offin disturbance."),
    Station("P02", "Pra Mid-Upper Reach", 5.711454, -1.588530, "monitor", 2,
            "Fills the ~50 km gap between the upper basin and the Beposo reach."),
    Station("P03", "Pra at Beposo Reach", 5.423526, -1.628935, "monitor", 3,
            "About 21 km above the Daboase abstraction; the primary "
            "early-warning station for the treatment plant."),
    Station("P04", "Pra Mid-Lower Reach", 5.345347, -1.620784, "monitor", 4,
            "Between Beposo and Daboase; used to check whether a signal is "
            "propagating downstream."),
    Station("P05", "Daboase Intake (GWCL)", 5.230010, -1.569200, "intake", 5,
            "The Ghana Water Company abstraction supplying Sekondi-Takoradi. "
            "This is the station the warning exists to protect."),
    Station("P06", "Pra Lower Reach", 5.145801, -1.653094, "downstream", 6,
            "Below the intake. Cannot provide early warning for Daboase; used "
            "to confirm whether an event propagated past the abstraction."),
    Station("P07", "Pra Lower Reach South", 5.137311, -1.648116, "downstream", 7,
            "Below the intake."),
    Station("P08", "Pra Estuary Approach", 5.109413, -1.614529, "downstream", 8,
            "Nearest station to the river mouth at Shama. Tidal influence is "
            "expected here, so its readings are not comparable to inland "
            "stations without care."),
]

ADDED_PATH = os.path.join("data", "network", "stations.json")


def _haversine_m(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = p2 - p1, radians(lon2 - lon1)
    h = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371008.8 * asin(sqrt(h))


def _insert_by_geography(chain, station):
    """Put a station where it makes the river chain shortest.

    A point on the Pra belongs between the two consecutive stations it lies
    between, and appending it to the end would make the upstream/downstream
    logic wrong for every station below it. Cheapest insertion -- the position
    that adds least total path length -- recovers that from coordinates alone,
    without needing the OSM centreline, which is itself unreliable in places.
    """
    if not chain:
        return [station]
    best, best_cost = 0, None
    for i in range(len(chain) + 1):
        before = chain[i - 1] if i else None
        after = chain[i] if i < len(chain) else None
        if before is None:
            cost = _haversine_m(station.lat, station.lon, after.lat, after.lon)
        elif after is None:
            cost = _haversine_m(before.lat, before.lon, station.lat, station.lon)
        else:
            cost = (_haversine_m(before.lat, before.lon, station.lat, station.lon)
                    + _haversine_m(station.lat, station.lon, after.lat, after.lon)
                    - _haversine_m(before.lat, before.lon, after.lat, after.lon))
        if best_cost is None or cost < best_cost:
            best, best_cost = i, cost
    return chain[:best] + [station] + chain[best:]


def load_added_stations(path=ADDED_PATH):
    """Stations appended from the Live Map, as raw dicts."""
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        doc = json.load(fh)
    return doc.get("stations", []) if isinstance(doc, dict) else list(doc)


def build_network(founding=None, added=None):
    """The full ordered station chain: founding stations plus added ones."""
    chain = sorted(founding if founding is not None else FOUNDING_STATIONS,
                   key=lambda s: s.order)
    known = {s.id for s in chain}
    for raw in (added if added is not None else load_added_stations()):
        if raw.get("id") in known:
            continue
        known.add(raw["id"])
        chain = _insert_by_geography(chain, Station(
            id=raw["id"], name=raw["name"],
            lat=float(raw["lat"]), lon=float(raw["lon"]),
            role=raw.get("role", "monitor"), order=0,
            description=raw.get("description", ""),
            place_source=raw.get("place_source", "provisional"),
            radius_m=float(raw.get("radius_m", 500.0))))
    for i, s in enumerate(chain, start=1):
        s.order = i
    return chain


STATIONS = build_network()

BY_ID = {s.id: s for s in STATIONS}
CONTROL_ID = "P01"
INTAKE_ID = "P05"


def control_station() -> Station:
    return BY_ID[CONTROL_ID]


def upstream_neighbour(station: Station):
    """The nearest station immediately upstream, or None for the first."""
    cands = [s for s in STATIONS if s.order == station.order - 1]
    return cands[0] if cands else None


def downstream_neighbour(station: Station):
    cands = [s for s in STATIONS if s.order == station.order + 1]
    return cands[0] if cands else None


# ---------------------------------------------------------------- settings ---

HISTORY_START = "2017-01-01"     # Sentinel-2 L2A archive depth on AWS
READING_MIN_PIXELS = 3           # absolute floor; below this a scene is unusable
QUALITY_GOOD_PIXELS = 150        # >= this many water pixels reads as GOOD
QUALITY_ACCEPTABLE_PIXELS = 40   # >= this is ACCEPTABLE, below is LOW_QUALITY

# Chronological split. Never shuffled: this is a time series and a random split
# would let the model learn from the future.
TRAIN_END = "2023-12-31"
VALIDATION_END = "2024-12-31"
# test = VALIDATION_END .. latest available

FEATURE_VERSION = "2.0"
CONTROL_MATCH_MAX_DAYS = 10      # how stale an upstream reading may be

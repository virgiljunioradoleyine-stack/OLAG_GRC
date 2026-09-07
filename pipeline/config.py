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


# Ordered upstream (order=1) to downstream (order=8). The Pra flows roughly
# north to south, reaching the sea near Shama at about 5.01 N.
STATIONS = [
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

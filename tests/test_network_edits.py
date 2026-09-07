"""Adding a station from the map: what the request may and may not do.

The request arrives from a public issue, so these tests are the security
boundary as much as the correctness one.
"""
import json
import os

import pytest

from pipeline.config import Station, build_network, _haversine_m
from scripts.add_station import (
    MIN_SEPARATION_M, Refused, add_station, match_candidate, next_station_id,
)

CANDIDATES = "web/public/data/candidates.geojson"


def _candidates():
    with open(CANDIDATES) as fh:
        return json.load(fh)["features"]


def _write_empty(path):
    with open(path, "w") as fh:
        json.dump({"stations": []}, fh)


pytestmark = pytest.mark.skipif(not os.path.exists(CANDIDATES),
                                reason="no candidate sites generated yet")


def test_an_unverified_point_is_refused():
    """The whole security model: only points the pipeline measured are allowed.

    Without this, a public issue could put a station anywhere -- on land, on a
    different river, on a neighbour's roof -- and the pipeline would dutifully
    collect nine years of meaningless readings for it.
    """
    with pytest.raises(Refused) as ex:
        match_candidate(5.5, -1.6, _candidates())
    assert "not a verified candidate" in str(ex.value)


def test_a_published_candidate_is_accepted():
    feat, moved = match_candidate(
        *reversed(_candidates()[0]["geometry"]["coordinates"][:2]), _candidates())
    assert moved < 1.0


def test_a_point_on_top_of_an_existing_station_is_refused(tmp_path):
    """Two stations metres apart measure the same water."""
    from pipeline.config import STATIONS
    st = STATIONS[0]
    fake = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"water_pixels": 200, "tile": "T30NXM"},
         "geometry": {"type": "Point", "coordinates": [st.lon, st.lat]}}]}
    cp = str(tmp_path / "cand.geojson")
    with open(cp, "w") as fh:
        json.dump(fake, fh)
    p = str(tmp_path / "stations.json")
    _write_empty(p)
    with pytest.raises(Refused) as ex:
        add_station(st.lat, st.lon, path=p, candidates_path=cp)
    assert st.id in str(ex.value)


def test_adding_inserts_by_geography_not_at_the_end(tmp_path):
    """A station between P01 and P02 must renumber the chain, not append.

    Appending would make every downstream station's upstream neighbour wrong,
    which is the input the control-point logic runs on.
    """
    p = str(tmp_path / "stations.json")
    _write_empty(p)
    # a point between P01 (5.875) and P02 (5.711)
    feat = min(_candidates(),
               key=lambda f: abs(f["geometry"]["coordinates"][1] - 5.80))
    lon, lat = feat["geometry"]["coordinates"][:2]
    rec = add_station(lat, lon, path=p, candidates_path=CANDIDATES)
    assert rec["order"] < rec["network_size"], "new station was pinned to the end"

    added = json.load(open(p))["stations"]
    chain = build_network(added=added)
    orders = [s.order for s in chain]
    assert orders == list(range(1, len(chain) + 1)), "chain is not densely ordered"
    founding = [s.id for s in chain if s.id != rec["id"]]
    assert founding == sorted(founding), "founding stations were reordered"


def test_ids_do_not_collide():
    existing = build_network()
    assert next_station_id(existing) not in {s.id for s in existing}


def test_added_stations_survive_a_reload(tmp_path):
    p = str(tmp_path / "stations.json")
    _write_empty(p)
    feat = _candidates()[0]
    lon, lat = feat["geometry"]["coordinates"][:2]
    rec = add_station(lat, lon, name="Somewhere", path=p, candidates_path=CANDIDATES)
    added = json.load(open(p))["stations"]
    chain = build_network(added=added)
    got = next(s for s in chain if s.id == rec["id"])
    assert got.name == "Somewhere"
    assert _haversine_m(got.lat, got.lon, lat, lon) < 1.0

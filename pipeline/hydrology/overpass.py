"""
River geometry and place names from OpenStreetMap, via the Overpass API.

Why OSM rather than HydroRIVERS: HydroRIVERS is the better hydrographic
product, but `data.hydrosheds.org` sits behind a Cloudflare interstitial and
returns 403 to any non-browser client (verified from CI on 2026-09-07 -- see
data/sources/probe_evidence.json). It cannot be acquired programmatically, and
the brief requires no manual downloads. Overpass is anonymous, returns JSON,
and gives us named, mapped river centrelines.

This replaces inferring the river's permanent course from a satellite water
mask. The MNDWI mask still decides which pixels hold water *today*; OSM
provides the authoritative channel geometry and the names.

OSM data is © OpenStreetMap contributors, licensed ODbL.
https://www.openstreetmap.org/copyright
"""
from __future__ import annotations

import os
import time

import requests

from ..io.atomic import read_json, write_json

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HYDRO_DIR = "data/hydrology"
RIVER_PATH = os.path.join(HYDRO_DIR, "pra_river.geojson")
PLACES_PATH = os.path.join(HYDRO_DIR, "places.json")

TIMEOUT = 180
MAX_RETRIES = 3
UA = {"User-Agent": "PraRiverWatch/1.0 (open-source river monitoring; +https://github.com/virgiljunioradoleyine-stack/OLAG_GRC)"}

# Bounding box covering the Pra from the upper basin to the sea at Shama.
PRA_BBOX = (5.00, -1.90, 6.00, -1.30)      # south, west, north, east


class OverpassUnavailable(RuntimeError):
    pass


def _query(ql):
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(OVERPASS_URL, data={"data": ql},
                              timeout=TIMEOUT, headers=UA)
            if r.status_code == 200:
                return r.json()
            last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as ex:
            last = ex
        if attempt < MAX_RETRIES - 1:
            time.sleep(5 * (attempt + 1))   # Overpass asks for gentle retries
    raise OverpassUnavailable(str(last))


def fetch_river_geometry(bbox=PRA_BBOX, name_regex="Pra", force=False):
    """Fetch the Pra's mapped centreline as GeoJSON LineStrings, cached."""
    if not force and os.path.exists(RIVER_PATH):
        return read_json(RIVER_PATH)

    s, w, n, e = bbox
    ql = f"""
[out:json][timeout:120];
(
  way["waterway"="river"]["name"~"{name_regex}",i]({s},{w},{n},{e});
  way["waterway"="riverbank"]["name"~"{name_regex}",i]({s},{w},{n},{e});
);
out geom;
"""
    data = _query(ql)
    features = []
    for el in data.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[p["lon"], p["lat"]] for p in geom],
            },
            "properties": {
                "osm_id": el.get("id"),
                "name": (el.get("tags") or {}).get("name"),
                "waterway": (el.get("tags") or {}).get("waterway"),
            },
        })
    if not features:
        raise OverpassUnavailable(
            f"no waterways matching /{name_regex}/i in {bbox}")

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source": "OpenStreetMap via Overpass API",
            "source_url": OVERPASS_URL,
            "license": "ODbL — © OpenStreetMap contributors",
            "license_url": "https://www.openstreetmap.org/copyright",
            "bbox": list(bbox),
            "segments": len(features),
        },
    }
    os.makedirs(HYDRO_DIR, exist_ok=True)
    write_json(RIVER_PATH, fc)
    return fc


def fetch_nearby_places(stations, radius_m=6000, force=False):
    """Nearest OSM-named settlement for each station, cached.

    Used so station labels come from the map rather than from us inventing
    place names we cannot verify.
    """
    if not force and os.path.exists(PLACES_PATH):
        return read_json(PLACES_PATH)

    parts = [
        f'node(around:{radius_m},{s.lat},{s.lon})'
        f'["place"~"city|town|village|suburb|hamlet"];'
        for s in stations
    ]
    ql = "[out:json][timeout:120];(" + "".join(parts) + ");out body;"
    data = _query(ql)

    nodes = [
        {"name": (el.get("tags") or {}).get("name"),
         "place": (el.get("tags") or {}).get("place"),
         "lat": el.get("lat"), "lon": el.get("lon")}
        for el in data.get("elements", [])
        if (el.get("tags") or {}).get("name")
    ]

    def hav(a_lat, a_lon, b_lat, b_lon):
        from math import asin, cos, radians, sin, sqrt
        dlat, dlon = radians(b_lat - a_lat), radians(b_lon - a_lon)
        h = (sin(dlat / 2) ** 2
             + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(dlon / 2) ** 2)
        return 2 * 6371000 * asin(sqrt(h))

    out = {}
    for s in stations:
        best, best_d = None, None
        for nd in nodes:
            d = hav(s.lat, s.lon, nd["lat"], nd["lon"])
            if best_d is None or d < best_d:
                best, best_d = nd, d
        out[s.id] = ({"nearest_place": best["name"], "place_type": best["place"],
                      "distance_m": round(best_d)} if best else
                     {"nearest_place": None, "place_type": None, "distance_m": None})

    payload = {"places": out, "radius_m": radius_m,
               "source": "OpenStreetMap via Overpass API",
               "license": "ODbL — © OpenStreetMap contributors"}
    os.makedirs(HYDRO_DIR, exist_ok=True)
    write_json(PLACES_PATH, payload)
    return payload


def load_river():
    return read_json(RIVER_PATH)


def load_places():
    return read_json(PLACES_PATH)

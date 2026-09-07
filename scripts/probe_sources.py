#!/usr/bin/env python3
"""
Probe candidate public data sources for reachability and anonymous access.

Run in GitHub Actions, where the runner has unrestricted internet. The local
development sandbox blocks every host except the Sentinel-2 bucket, so this is
how we establish -- with evidence rather than assumption -- which sources the
production pipeline can actually rely on.

Records: HTTP status, whether an account/key was needed, response shape, and a
small sample of the payload so the schema can be designed against reality.
"""
from __future__ import annotations

import json
import sys
import time

import requests

TIMEOUT = 45
UA = {"User-Agent": "PraRiverWatch/1.0 (+https://github.com/virgiljunioradoleyine-stack/OLAG_GRC)"}

# lat/lon of the Daboase intake, used for point queries
LAT, LON = 5.230010, -1.569200

CANDIDATES = [
    # ---- rainfall -------------------------------------------------------
    ("rainfall", "NASA POWER daily point",
     f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR"
     f"&community=AG&longitude={LON}&latitude={LAT}&start=20240101&end=20240110&format=JSON"),
    ("rainfall", "Open-Meteo ERA5 archive",
     f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}"
     f"&start_date=2024-01-01&end_date=2024-01-10&daily=precipitation_sum&timezone=UTC"),
    ("rainfall", "CHIRPS UCSB africa_daily dir",
     "https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_daily/tifs/p05/2024/"),
    ("rainfall", "CHIRPS UCSB single daily tif",
     "https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_daily/tifs/p05/2024/"
     "chirps-v2.0.2024.01.01.tif.gz"),
    # ---- river geometry -------------------------------------------------
    ("hydrology", "Overpass API (osm rivers bbox)",
     "https://overpass-api.de/api/interpreter?data=%5Bout%3Ajson%5D%3Bway%285.2%2C-1.7%2C5.3%2C-1.5%29%5Bwaterway%3Driver%5D%3Bout%20ids%3B"),
    ("hydrology", "Overpass kumi mirror",
     "https://overpass.kumi.systems/api/interpreter?data=%5Bout%3Ajson%5D%3Bway%285.2%2C-1.7%2C5.3%2C-1.5%29%5Bwaterway%3Driver%5D%3Bout%20ids%3B"),
    ("hydrology", "HydroRIVERS Africa (HEAD only)",
     "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_af_shp.zip"),
    # ---- basemap tiles --------------------------------------------------
    ("tiles", "Esri World Imagery",
     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/8/119/247"),
    ("tiles", "OSM standard",
     "https://tile.openstreetmap.org/8/247/119.png"),
    ("tiles", "Esri World Topo",
     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/8/119/247"),
    # ---- satellite (known good, control) --------------------------------
    ("satellite", "sentinel-cogs S3 listing",
     "https://sentinel-cogs.s3.us-west-2.amazonaws.com/?list-type=2&prefix=sentinel-s2-l2a-cogs/30/N/XL/2026/7/&delimiter=/&max-keys=3"),
    ("satellite", "Earth Search STAC root",
     "https://earth-search.aws.element84.com/v1"),
    # ---- ground truth hunting -------------------------------------------
    ("groundtruth", "data.gov.gh CKAN package_list",
     "https://data.gov.gh/api/3/action/package_list"),
    ("groundtruth", "GEMStat portal",
     "https://gemstat.org/"),
    ("groundtruth", "WQP (US, schema reference only)",
     "https://www.waterqualitydata.us/data/Result/search?statecode=US%3A01&characteristicName=Turbidity&startDateLo=01-01-2024&startDateHi=01-05-2024&mimeType=csv&zip=no"),
]


def probe(url):
    t0 = time.time()
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=UA, stream=True)
        head = r.raw.read(2048, decode_content=True) or b""
        r.close()
        return {
            "status": r.status_code,
            "ok": r.ok,
            "seconds": round(time.time() - t0, 2),
            "content_type": r.headers.get("content-type", ""),
            "content_length": r.headers.get("content-length", ""),
            "sample": head[:700].decode("utf-8", "replace"),
        }
    except Exception as ex:
        return {"status": None, "ok": False, "seconds": round(time.time() - t0, 2),
                "error": f"{type(ex).__name__}: {ex}"[:300]}


def main():
    results = []
    for group, name, url in CANDIDATES:
        res = probe(url)
        res.update(group=group, name=name, url=url)
        results.append(res)
        flag = "OK  " if res["ok"] else "FAIL"
        print(f"[{flag}] {group:11s} {name:38s} status={res.get('status')} "
              f"{res.get('seconds')}s {res.get('content_type','')[:40]}")
        if res.get("error"):
            print(f"          error: {res['error']}")
        elif res.get("sample"):
            s = " ".join(res["sample"].split())[:260]
            print(f"          sample: {s}")
        print()

    with open("probe_results.json", "w") as fh:
        json.dump(results, fh, indent=2)

    print("=" * 72)
    print("REACHABLE, ANONYMOUS:")
    for r in results:
        if r["ok"]:
            print(f"  {r['group']:11s} {r['name']}")
    print("\nNOT REACHABLE:")
    for r in results:
        if not r["ok"]:
            print(f"  {r['group']:11s} {r['name']}  ({r.get('status') or r.get('error','')[:60]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

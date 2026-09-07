"""STEP 0 / Check 1 — Earth Search STAC connectivity."""
import json, sys, datetime as dt
import requests

STAC = "https://earth-search.aws.element84.com/v1/search"
CONTROL = {"id": "control", "name": "Pra Upstream (Control)", "lat": 6.2100, "lon": -1.6500}

def bbox(lat, lon, pad=0.01):
    return [lon - pad, lat - pad, lon + pad, lat + pad]

def main():
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox(CONTROL["lat"], CONTROL["lon"]),
        "datetime": "2024-01-01T00:00:00Z/2026-09-07T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": 20}},
        "limit": 100,
    }
    print("POST", STAC)
    print("bbox:", body["bbox"])
    r = requests.post(STAC, json=body, timeout=60)
    print("HTTP", r.status_code)
    r.raise_for_status()
    d = r.json()
    feats = d.get("features", [])
    print("matched (server):", d.get("context", {}).get("matched") or d.get("numberMatched"))
    print("returned this page:", len(feats))
    if not feats:
        print("FAIL: no scenes returned")
        return 1
    feats.sort(key=lambda f: f["properties"]["datetime"], reverse=True)
    for f in feats[:3]:
        p = f["properties"]
        print(f"  id={f['id']}  date={p['datetime'][:10]}  cloud={p.get('eo:cloud_cover'):.2f}%")
    print("\nassets on first scene:", sorted(feats[0]["assets"].keys()))
    with open("scripts/_check1_scene.json", "w") as fh:
        json.dump(feats[0], fh, indent=2)
    print("saved first scene -> scripts/_check1_scene.json")
    print("PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())

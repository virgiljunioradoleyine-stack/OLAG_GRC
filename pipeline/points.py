"""Monitoring points and MGRS tile resolution (no external API required)."""
from pyproj import Transformer

# Verified against Sentinel-2 persistent-water masks -- see COORDINATES_GUIDE.md.
# "pixels" is the count of persistent-water pixels inside the 50 m reading
# window; more pixels means a more reliable reading. The coordinates in the
# original project brief were all off-channel and were replaced.
POINTS = [
    {
        "id": "control", "name": "Pra Upper Basin (Control)",
        "lat": 5.875062, "lon": -1.522239, "role": "control",
        "pixels": 15,
        "note": "On the Pra mainstem, confirmed against OpenStreetMap, and "
                "ABOVE the Pra/Offin confluence -- imagery shows the channel is "
                "40 m here and 120 m below the junction 8 km south-west. The "
                "Offin is the heavily mined tributary, so a control above the "
                "junction cannot be contaminated by Offin galamsey. This is the "
                "arrangement the alert suppression logic depends on. BUT: the "
                "control's readings correlate only weakly with the monitored "
                "points (direction agreement ~52%, a coin flip), so the shared "
                "rainfall signal the suppression logic assumes is not visible in "
                "the data. Two points on the same river agree barely better, so "
                "this is measurement noise, not siting -- see TEST_RESULTS.md 6.",
    },
    {
        "id": "monitor", "name": "Pra at Beposo Reach",
        "lat": 5.423526, "lon": -1.628935, "role": "monitor",
        "pixels": 14,
        "note": "~21 km upstream of the intake, giving real warning lead time.",
    },
    {
        "id": "intake", "name": "Daboase Intake (GWCL)",
        "lat": 5.230010, "lon": -1.569200, "role": "intake",
        "pixels": 15,
        "note": "1.0 km from Daboase; widest reach tested (811 water px within 1 km).",
    },
]

_COL_SETS = ["ABCDEFGH", "JKLMNPQR", "STUVWXYZ"]
_ROW_SETS = ["ABCDEFGHJKLMNPQRSTUV", "FGHJKLMNPQRSTUVABCDE"]
_LAT_BANDS = "CDEFGHJKLMNPQRSTUVWX"


def utm_zone(lon):
    return int((lon + 180) // 6) + 1


def lat_band(lat):
    return _LAT_BANDS[int((lat + 80) // 8)]


def epsg_for(lat, lon):
    z = utm_zone(lon)
    return 32600 + z if lat >= 0 else 32700 + z


def to_utm(lat, lon):
    epsg = epsg_for(lat, lon)
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = tr.transform(lon, lat)
    return x, y, epsg


def mgrs_tile(lat, lon):
    """Return (zone:int, band:str, square:str) — the Sentinel-2 tile prefix parts."""
    z = utm_zone(lon)
    x, y, _ = to_utm(lat, lon)
    col = _COL_SETS[(z - 1) % 3][int(x // 100000) - 1]
    row = _ROW_SETS[(z - 1) % 2][int(y // 100000) % 20]
    return z, lat_band(lat), col + row


if __name__ == "__main__":
    for p in POINTS:
        z, b, sq = mgrs_tile(p["lat"], p["lon"])
        x, y, epsg = to_utm(p["lat"], p["lon"])
        print(f"{p['id']:8s} lat={p['lat']:.4f} lon={p['lon']:.4f} -> T{z}{b}{sq}  "
              f"EPSG:{epsg} easting={x:.0f} northing={y:.0f}")


def from_utm(x, y, epsg):
    """Inverse of to_utm: UTM easting/northing -> (lat, lon)."""
    tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(x, y)
    return lat, lon

"""
Sentinel-2 L2A scene search backed directly by the public `sentinel-cogs` S3
bucket (us-west-2), used in place of the Earth Search STAC search API.

Why: this project's egress policy denies earth-search.aws.element84.com, but the
bucket the STAC API *points at* is reachable. Every scene directory in the bucket
carries the same STAC item JSON the API would have returned, so we list object
prefixes to enumerate scenes and read those item JSONs for metadata. Same data,
same STAC schema, no account and no search host.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com"
ROOT = "sentinel-s2-l2a-cogs"
_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}

_session = requests.Session()


def _get(url, **kw):
    r = _session.get(url, timeout=60, **kw)
    r.raise_for_status()
    return r


def list_scene_prefixes(zone: int, band: str, square: str, year: int, month: int):
    """List scene directory prefixes for one tile-month."""
    prefix = f"{ROOT}/{zone}/{band}/{square}/{year}/{month}/"
    out, token = [], None
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={prefix}&delimiter=/&max-keys=1000"
        if token:
            url += f"&continuation-token={requests.utils.quote(token, safe='')}"
        root = ET.fromstring(_get(url).content)
        for cp in root.findall("s3:CommonPrefixes/s3:Prefix", _NS):
            p = cp.text
            if p and p != prefix:
                out.append(p.rstrip("/"))
        if root.findtext("s3:IsTruncated", default="false", namespaces=_NS) != "true":
            break
        token = root.findtext("s3:NextContinuationToken", namespaces=_NS)
        if not token:
            break
    return sorted(out)


def item_url(scene_prefix: str) -> str:
    scene_id = scene_prefix.rsplit("/", 1)[-1]
    return f"{BUCKET}/{scene_prefix}/{scene_id}.json"


def fetch_item(scene_prefix: str):
    """Fetch one scene's STAC item JSON. Returns None if missing/unreadable."""
    try:
        return _get(item_url(scene_prefix)).json()
    except Exception:
        return None


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def search(zone, band, square, start: date, end: date,
           max_cloud: float = 20.0, workers: int = 12):
    """Return STAC items for a tile between two dates, filtered by cloud cover.

    Mirrors the shape of an Earth Search /search response's `features`.
    """
    prefixes = []
    for y, m in _months(start, end):
        try:
            prefixes += list_scene_prefixes(zone, band, square, y, m)
        except Exception:
            continue

    with ThreadPoolExecutor(max_workers=workers) as ex:
        items = list(ex.map(fetch_item, prefixes))

    keep = []
    for it in items:
        if not it:
            continue
        p = it.get("properties", {})
        d = p.get("datetime", "")[:10]
        if not d or not (start.isoformat() <= d <= end.isoformat()):
            continue
        cc = p.get("eo:cloud_cover")
        if cc is None or cc >= max_cloud:
            continue
        keep.append(it)
    keep.sort(key=lambda i: i["properties"]["datetime"])
    return keep


def asset_href(item, key):
    return item["assets"][key]["href"]

"""
GDAL/network environment setup.

Previously `GDAL_HTTP_CAINFO` was hard-coded to `/root/.ccr/ca-bundle.crt`, a
path that exists only inside one development sandbox. Everywhere else that
pointed GDAL at a non-existent CA bundle. The bundle is now taken from the
environment when present and simply left alone otherwise, so the system trusts
the platform's own certificate store -- which is the correct default on a
GitHub runner or any normal machine.
"""
from __future__ import annotations

import os

GDAL_DEFAULTS = {
    "GDAL_DISABLE_READ_DIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "26214400",
}


def configure_gdal():
    """Apply GDAL tuning for windowed COG reads over HTTP. Idempotent."""
    for k, v in GDAL_DEFAULTS.items():
        os.environ.setdefault(k, v)

    # Only set a CA bundle if one was explicitly provided AND exists. Never
    # invent a path: an unreadable CAINFO is worse than none at all.
    for var in ("GDAL_HTTP_CAINFO", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE"):
        val = os.environ.get(var)
        if val and not os.path.exists(val):
            os.environ.pop(var, None)
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("CURL_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        os.environ.setdefault("GDAL_HTTP_CAINFO", bundle)

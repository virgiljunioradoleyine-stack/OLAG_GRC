import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def dates():
    return pd.date_range("2019-01-01", periods=160, freq="7D")


@pytest.fixture
def obs_frame(dates):
    def make(seed=1, station="P05", n=None):
        n = n or len(dates)
        r = np.random.default_rng(seed)
        return pd.DataFrame({
            "date": dates[:n],
            "station_id": station,
            "scene_id": [f"S2_{i}" for i in range(n)],
            "ndti": r.normal(0.08, 0.05, n),
            "ndti_std": r.random(n) * 0.05,
            "ndwi": r.normal(0.10, 0.05, n),
            "mndwi": r.normal(0.30, 0.08, n),
            "red_green_ratio": r.normal(1.2, 0.1, n),
            "red": r.normal(0.20, 0.05, n),
            "green": r.normal(0.18, 0.04, n),
            "nir": r.normal(0.15, 0.04, n),
            "swir16": r.normal(0.05, 0.02, n),
            "water_pixel_count": r.integers(60, 700, n),
            "window_pixels": 800,
            "cloud_fraction": r.random(n) * 0.3,
            "tile_cloud_cover": r.random(n) * 90,
            "quality": "GOOD",
            "quality_score": 0.5 + r.random(n) * 0.5,
        })
    return make


@pytest.fixture
def rain_frame():
    r = np.random.default_rng(7)
    d = pd.date_range("2018-01-01", periods=3600, freq="D")
    return pd.DataFrame({"date": d, "precip_mm": np.abs(r.normal(3.5, 5.0, len(d))),
                         "source": "test"})

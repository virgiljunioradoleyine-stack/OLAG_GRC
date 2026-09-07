"""Data-integrity tests over whatever the pipeline has actually produced."""
import os

import numpy as np
import pandas as pd
import pytest

from pipeline.config import BY_ID, STATIONS
from pipeline.satellite.observations import OBS_FIELDS, load_observations

OBS_PATH = "data/observations/observations.csv"
pytestmark = pytest.mark.skipif(not os.path.exists(OBS_PATH),
                                reason="no observations collected yet")


def test_schema_columns_present():
    df = load_observations()
    assert list(df.columns) == OBS_FIELDS


def test_no_duplicate_station_dates():
    df = load_observations()
    dup = df.duplicated(subset=["station_id", "date"]).sum()
    assert dup == 0, f"{dup} duplicate station/date rows"


def test_dates_are_chronological_per_station():
    df = load_observations()
    for sid, g in df.groupby("station_id"):
        assert g["date"].is_monotonic_increasing, f"{sid} dates out of order"


def test_station_ids_are_known():
    df = load_observations()
    unknown = set(df["station_id"]) - set(BY_ID)
    assert not unknown, f"observations reference unknown stations: {unknown}"


def test_indices_are_in_physical_range():
    df = load_observations()
    for col in ("ndti", "ndwi", "mndwi"):
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        assert v.between(-1, 1).all(), f"{col} outside [-1, 1]"


def test_reflectances_are_non_negative():
    df = load_observations()
    for col in ("red", "green", "nir", "swir16"):
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        assert (v >= -0.05).all(), f"{col} has physically impossible values"


def test_quality_labels_are_valid():
    from pipeline.satellite.quality import QUALITY_LEVELS
    df = load_observations()
    assert set(df["quality"]).issubset(set(QUALITY_LEVELS))


def test_rejected_observations_are_not_stored():
    df = load_observations()
    assert (df["quality"] != "REJECTED").all(), \
        "rejected observations should never reach the dataset"


def test_station_coordinates_are_valid():
    for s in STATIONS:
        assert -90 <= s.lat <= 90 and -180 <= s.lon <= 180
        assert 4.0 < s.lat < 7.5 and -3.5 < s.lon < -0.5, \
            f"{s.id} is outside the Pra basin"


def test_station_order_is_unique_and_dense():
    orders = sorted(s.order for s in STATIONS)
    assert orders == list(range(1, len(STATIONS) + 1))


def test_incremental_write_preserves_history(tmp_path):
    """A 90-day scheduled run must never wipe nine years of record."""
    import os
    from pipeline.satellite.observations import OBS_FIELDS, write_observations

    p = str(tmp_path / "obs.csv")
    blank = {k: "" for k in OBS_FIELDS}
    history = [{**blank, "date": f"2017-01-{i:02d}", "station_id": "P05",
                "ndti": 0.05, "water_pixel_count": 100} for i in range(1, 21)]
    write_observations(history, p, merge=False)

    recent = [{**blank, "date": f"2026-09-{i:02d}", "station_id": "P05",
               "ndti": 0.09, "water_pixel_count": 300} for i in range(1, 4)]
    write_observations(recent, p)

    df = load_observations(p)
    assert len(df) == 23, "incremental write destroyed the historical record"
    assert str(df["date"].min().date()) == "2017-01-01"


def test_replace_is_explicit(tmp_path):
    from pipeline.satellite.observations import OBS_FIELDS, write_observations
    p = str(tmp_path / "obs.csv")
    blank = {k: "" for k in OBS_FIELDS}
    write_observations([{**blank, "date": "2017-01-01", "station_id": "P05",
                         "ndti": 0.05, "water_pixel_count": 100}], p, merge=False)
    write_observations([{**blank, "date": "2026-09-01", "station_id": "P05",
                         "ndti": 0.09, "water_pixel_count": 300}], p, merge=False)
    assert len(load_observations(p)) == 1

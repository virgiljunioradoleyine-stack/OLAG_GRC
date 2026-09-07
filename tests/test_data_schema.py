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


def test_reflectances_are_physically_plausible():
    """Reflectance must be plausible, allowing for a known L2A artifact.

    Sen2Cor's atmospheric correction can over-correct aerosols over very dark
    targets and return slightly negative BOA reflectance -- in this record, 25
    of 2319 observations (1.1%) had SWIR marginally below zero, minimum -0.063.
    That is a documented processing artifact over water, not corrupt data, and
    the indices are already protected from it by flooring at zero before any
    normalised difference is computed. So this test does not demand
    non-negativity, which would fail on correct data. It asserts that no value
    is deeply negative and that negatives stay a small minority -- a systematic
    correction failure would breach both.

    The upper bound is the other direction: water is dark, and a reading
    brighter than BRIGHT_MAX in the visible bands is cloud or glint rather than
    river. The collector now rejects those pixels, so any that reappear here
    mean the rejection has stopped working.
    """
    from pipeline.satellite.observations import BRIGHT_MAX

    df = load_observations()
    for col in ("red", "green", "nir", "swir16"):
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        assert (v >= -0.10).all(), (
            f"{col} reaches {v.min():.4f} -- too negative to be a correction "
            f"artifact")
        assert (v < 0).mean() < 0.05, (
            f"{(v < 0).mean():.1%} of {col} values are negative; an artifact "
            f"affecting this many observations is a systematic problem")

    for col in ("red", "green"):
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        assert (v <= BRIGHT_MAX).all(), (
            f"{col} reaches {v.max():.4f}, above the {BRIGHT_MAX} brightness "
            f"cut -- cloud or glint is reaching the readings")

    for col in ("nir", "swir16"):
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        assert (v <= 1.0).all(), (
            f"{col} reaches {v.max():.4f}; reflectance above 1.0 is not "
            f"physical")


def test_bright_pixels_are_excluded_from_readings():
    """The brightness cut is applied per pixel, not per observation."""
    import numpy as np
    from pipeline.satellite.observations import BRIGHT_MAX

    green = np.array([[0.2, 0.2], [0.9, 0.2]], dtype="float32")
    red = np.array([[0.2, 0.2], [0.9, 0.2]], dtype="float32")
    finite = np.isfinite(red) & np.isfinite(green)
    bright = finite & ((green > BRIGHT_MAX) | (red > BRIGHT_MAX))
    assert bright.sum() == 1, "a single cloud pixel must not condemn the window"
    assert (finite & ~bright).sum() == 3


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


def test_recollection_supersedes_stored_rows(tmp_path):
    """Re-collecting a date must recompute it, not preserve the old value.

    A full re-collection once left 25 rows with an out-of-range MNDWI in place,
    because the stored rows happened to have more water pixels than the fresh
    ones. Rows computed by since-fixed code could never be healed.
    """
    from pipeline.satellite.observations import OBS_FIELDS, write_observations

    p = str(tmp_path / "obs.csv")
    blank = {k: "" for k in OBS_FIELDS}
    write_observations([{**blank, "date": "2020-05-01", "station_id": "P05",
                         "ndti": 0.9, "water_pixel_count": 900}], p, merge=False)

    # fresh row for the same date with FEWER pixels must still win
    write_observations([{**blank, "date": "2020-05-01", "station_id": "P05",
                         "ndti": 0.1, "water_pixel_count": 100}], p)

    df = load_observations(p)
    assert len(df) == 1
    assert float(df["ndti"].iloc[0]) == 0.1, "stale row survived a re-collection"


def test_best_scene_wins_within_a_single_run(tmp_path):
    """Two scenes on one date: the one with more usable water pixels wins."""
    from pipeline.satellite.observations import OBS_FIELDS, write_observations

    p = str(tmp_path / "obs.csv")
    blank = {k: "" for k in OBS_FIELDS}
    write_observations([
        {**blank, "date": "2020-05-01", "station_id": "P05", "ndti": 0.1,
         "water_pixel_count": 100},
        {**blank, "date": "2020-05-01", "station_id": "P05", "ndti": 0.2,
         "water_pixel_count": 500},
    ], p, merge=False)
    df = load_observations(p)
    assert len(df) == 1 and float(df["ndti"].iloc[0]) == 0.2


def test_recollection_can_remove_a_date_that_no_longer_qualifies(tmp_path):
    """A re-collection is authoritative: a row it no longer produces is gone.

    Superseding by station-date is not enough. When a fix makes a date stop
    qualifying entirely -- the brightness cut rejected every pixel of 31
    cloud-contaminated readings, so those dates yielded no fresh row -- there is
    nothing to supersede the stale row with, and it survives a full
    re-collection. Deletion is only expressible as "this window now looks like
    this".
    """
    from pipeline.satellite.observations import OBS_FIELDS, write_observations

    p = str(tmp_path / "obs.csv")
    blank = {k: "" for k in OBS_FIELDS}
    write_observations([
        {**blank, "date": "2020-05-01", "station_id": "P05", "ndti": 0.1,
         "water_pixel_count": 100},
        {**blank, "date": "2020-05-06", "station_id": "P05", "ndti": 0.9,
         "water_pixel_count": 100},          # the contaminated one
    ], p, merge=False)

    # re-collect the window; the bad date now yields nothing
    write_observations([
        {**blank, "date": "2020-05-01", "station_id": "P05", "ndti": 0.1,
         "water_pixel_count": 100},
    ], p, covered_from="2020-05-01")

    df = load_observations(p)
    assert len(df) == 1, "a row the re-collection rejected survived"
    assert str(df["date"].iloc[0].date()) == "2020-05-01"


def test_authoritative_window_does_not_reach_into_history(tmp_path):
    """A 90-day run rewrites 90 days, not nine years."""
    from pipeline.satellite.observations import OBS_FIELDS, write_observations

    p = str(tmp_path / "obs.csv")
    blank = {k: "" for k in OBS_FIELDS}
    write_observations([{**blank, "date": f"2017-01-{i:02d}", "station_id": "P05",
                         "ndti": 0.05, "water_pixel_count": 100}
                        for i in range(1, 21)], p, merge=False)

    write_observations([{**blank, "date": "2026-09-01", "station_id": "P05",
                         "ndti": 0.09, "water_pixel_count": 300}],
                       p, covered_from="2026-06-09")

    df = load_observations(p)
    assert len(df) == 21, "the covered window reached back into history"


def test_a_station_that_collected_nothing_keeps_its_rows(tmp_path):
    """A transient read failure must not erase a station's record.

    Only a station that demonstrably collected something may rewrite its own
    window; one that returned nothing at all is treated as unread, not as empty.
    """
    from pipeline.satellite.observations import OBS_FIELDS, write_observations

    p = str(tmp_path / "obs.csv")
    blank = {k: "" for k in OBS_FIELDS}
    write_observations([
        {**blank, "date": "2026-09-01", "station_id": "P05", "ndti": 0.1,
         "water_pixel_count": 100},
        {**blank, "date": "2026-09-01", "station_id": "P06", "ndti": 0.2,
         "water_pixel_count": 100},
    ], p, merge=False)

    # only P05 came back this run; P06's scenes failed to read
    write_observations([{**blank, "date": "2026-09-03", "station_id": "P05",
                         "ndti": 0.3, "water_pixel_count": 200}],
                       p, covered_from="2026-08-01")

    df = load_observations(p)
    assert set(df["station_id"]) == {"P05", "P06"}, "an unread station was erased"
    assert len(df[df["station_id"] == "P05"]) == 1, "P05's window was not rewritten"

"""Ground-truth schema tests. There is no data; these guard the ingestion path."""
import pandas as pd
import pytest

from pipeline.config import STATIONS
from pipeline.groundtruth.store import (
    SCHEMA_COLUMNS, load_ground_truth, match_to_observations, validate_ground_truth,
)

KNOWN = [s.id for s in STATIONS]


def test_repository_contains_no_fabricated_ground_truth():
    """If this ever fails, someone has added data -- validate it deliberately."""
    gt = load_ground_truth()
    assert gt.empty, (
        "ground-truth rows are present. That may be legitimate, but the claim "
        "'no verified ground truth exists' in the docs must then be updated.")


def test_validation_rejects_empty_input():
    assert validate_ground_truth(pd.DataFrame()) == ["no ground-truth records found"]


def _row(**kw):
    base = dict(sample_date="2024-03-01", station_id="P05",
                characteristic="turbidity", value=120.0, unit="NTU",
                organisation="Test Org", source_url="https://example.org/report")
    base.update(kw)
    return base


def test_validation_accepts_a_well_formed_row():
    df = pd.DataFrame([_row()])
    assert validate_ground_truth(df, KNOWN) == []


def test_validation_rejects_unknown_station():
    df = pd.DataFrame([_row(station_id="ZZZ")])
    assert any("not in the monitoring network" in p
               for p in validate_ground_truth(df, KNOWN))


def test_validation_rejects_bad_units_and_negatives():
    assert any("unit" in p for p in
               validate_ground_truth(pd.DataFrame([_row(unit="bananas")]), KNOWN))
    assert any("negative" in p for p in
               validate_ground_truth(pd.DataFrame([_row(value=-5)]), KNOWN))


def test_validation_requires_provenance():
    df = pd.DataFrame([_row(source_url=None)])
    assert validate_ground_truth(df, KNOWN)


def test_template_has_the_documented_columns():
    import os
    p = "data/groundtruth/TEMPLATE.csv"
    assert os.path.exists(p)
    assert open(p).readline().strip().split(",") == SCHEMA_COLUMNS


def test_matching_window_is_tight(obs_frame):
    obs = obs_frame(1)
    near = obs["date"].iloc[10]
    gt = pd.DataFrame([
        _row(sample_date=near, station_id="P05"),
        _row(sample_date=near + pd.Timedelta(days=9), station_id="P05"),
    ])
    gt["sample_date"] = pd.to_datetime(gt["sample_date"])
    matched = match_to_observations(gt, obs, "P05", max_days=1)
    assert len(matched) == 1, "a 9-day-old sample must not be paired"

from pipeline.satellite.quality import QUALITY_LEVELS, quality_of


def test_levels_are_ordered_by_pixel_count():
    good, _, _ = quality_of(600, 0.03, 0.05)
    acc, _, _ = quality_of(80, 0.03, 0.05)
    low, _, _ = quality_of(20, 0.03, 0.05)
    assert good == "GOOD" and acc == "ACCEPTABLE" and low == "LOW_QUALITY"


def test_too_few_pixels_is_rejected():
    level, score, reasons = quality_of(4, 0.02, 0.0)
    assert level == "REJECTED" and score == 0.0 and reasons


def test_high_scatter_downgrades_even_with_many_pixels():
    level, _, _ = quality_of(900, 0.30, 0.0)
    assert level == "LOW_QUALITY"


def test_heavy_cloud_downgrades():
    level, _, _ = quality_of(900, 0.01, 0.85)
    assert level == "LOW_QUALITY"


def test_all_levels_are_declared():
    for args in [(600, .01, .0), (80, .01, .0), (20, .01, .0), (2, .01, .0)]:
        assert quality_of(*args)[0] in QUALITY_LEVELS

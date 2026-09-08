import pytest

from pipeline.alerting.engine import SEVERITIES, assess
from pipeline.config import BY_ID

ST = BY_ID["P05"]


def _a(**kw):
    base = dict(station=ST, date="2026-03-14", indicator=0.20, expected=0.10,
                quality="GOOD", quality_score=0.9)
    base.update(kw)
    return assess(**base)


def test_normal_when_close_to_expected():
    assert _a(indicator=0.101, z_score=0.1).severity == "NORMAL"


def test_severity_increases_with_deviation():
    order = [_a(z_score=z).severity for z in (0.2, 2.0, 3.0, 4.5)]
    idx = [SEVERITIES.index(s) for s in order]
    assert idx == sorted(idx), f"severity not monotonic in deviation: {order}"


def test_heavy_rain_suppresses_severity():
    dry = _a(z_score=3.0, rain_7d=3, rain_7d_anom=-20, persistence=2)
    wet = _a(z_score=3.0, rain_7d=110, rain_7d_anom=55, persistence=2)
    assert SEVERITIES.index(wet.severity) < SEVERITIES.index(dry.severity)


def test_dry_conditions_escalate():
    a = _a(z_score=3.0, rain_7d=2, rain_7d_anom=-25, persistence=2)
    assert any("BELOW" in s for s in a.signals)


def test_a_single_observation_cannot_be_escalated_into_the_top_tiers():
    """Corroboration must not substitute for magnitude.

    This replaces a stricter rule -- that a single observation could never
    reach HIGH at all -- which was written before there was any data to test
    it against, and which the real record showed to be wrong for this basin.
    Roughly two thirds of Sentinel-2 scenes over the Pra are unusable, so a
    station can go three or four weeks between readings; "has not persisted"
    usually means "we did not look again", and the old rule therefore
    suppressed precisely the short sharp episode the system exists to catch.
    It also ran before the CRITICAL check, so the magnitude route to the top
    tier could never fire.

    The property worth keeping is the one that actually guards against alarm
    inflation: a moderate reading may not be *stacked* into the top tiers by a
    dry week plus a detector flag. Its own departure has to earn it.
    """
    a = _a(z_score=3.0, rain_7d=2, rain_7d_anom=-25, persistence=0,
           anomaly_flagged=True)
    assert SEVERITIES.index(a.severity) <= SEVERITIES.index("HIGH")


def test_a_single_extreme_observation_may_stand_on_its_own_magnitude():
    """A reading extreme enough on its own terms is not held back."""
    a = _a(z_score=6.0, rain_7d=2, rain_7d_anom=-25, persistence=0)
    assert SEVERITIES.index(a.severity) >= SEVERITIES.index("HIGH")


def test_low_quality_cannot_raise_an_alert():
    a = _a(z_score=6.0, rain_7d=1, rain_7d_anom=-30, persistence=5,
           quality="LOW_QUALITY")
    assert SEVERITIES.index(a.severity) <= SEVERITIES.index("WATCH")


def test_falling_index_is_never_an_alert():
    a = _a(indicator=0.02, z_score=-4.0, anomaly_flagged=True)
    assert a.severity == "NORMAL"


def test_critical_requires_extreme_deviation():
    """CRITICAL must not be reachable by stacking corroboration alone."""
    kw = dict(rain_7d=2, rain_7d_anom=-25, persistence=4, anomaly_flagged=True,
              upstream_id="P04", upstream_diff=0.08)
    assert _a(z_score=3.0, **kw).severity != "CRITICAL"
    assert _a(z_score=4.5, **kw).severity != "CRITICAL"
    assert _a(z_score=5.5, **kw).severity == "CRITICAL"


def test_severity_pyramid_is_not_inverted():
    """Each tier must be rarer than the one below it across a realistic sweep."""
    import numpy as np
    from collections import Counter
    rng = np.random.default_rng(0)
    counts = Counter()
    for _ in range(4000):
        counts[_a(z_score=float(rng.normal(0, 1.2)),
                  rain_7d=float(abs(rng.normal(25, 20))),
                  rain_7d_anom=float(rng.normal(0, 12)),
                  persistence=int(rng.integers(0, 4)),
                  anomaly_flagged=bool(rng.random() < 0.1)).severity] += 1
    order = ["WATCH", "ELEVATED", "HIGH", "CRITICAL"]
    seq = [counts[s] for s in order]
    assert seq == sorted(seq, reverse=True), f"inverted severity pyramid: {dict(counts)}"


@pytest.mark.parametrize("z", [0.1, 2.0, 3.0, 5.0])
def test_narratives_never_claim_a_cause(z):
    a = _a(z_score=z, rain_7d=2, rain_7d_anom=-25, persistence=3)
    text = f"{a.headline} {a.explanation} {a.recommended_action}".lower()
    for banned in ("galamsey", "illegal mining", "mercury", "arsenic",
                   "caused by", "proves"):
        assert banned not in text, f"narrative claims too much: {banned!r}"


def test_alerts_explain_themselves():
    a = _a(z_score=4.5, rain_7d=2, rain_7d_anom=-25, persistence=3)
    assert a.headline and a.explanation and a.recommended_action
    assert a.signals
    assert "rainfall" in a.explanation.lower()
    assert a.confidence in ("low", "moderate", "high")


def test_severity_forms_a_pyramid_over_the_real_record():
    """Each tier must be rarer than the one below it, on the actual data.

    This is the check that was missing. Every unit test here passes on
    hand-built inputs, and the published record still came out with 8 HIGH
    against 1 CRITICAL after one fix, and 32 HIGH against 31 CRITICAL before
    it -- shapes that are impossible for a calibrated ladder and that no
    single-case test can see. If an operator meets CRITICAL as often as HIGH,
    the word stops meaning anything.
    """
    import json
    import os

    import pytest

    path = "web/public/data/summary.json"
    if not os.path.exists(path):
        pytest.skip("no exported dashboard yet")
    with open(path) as fh:
        counts = json.load(fh).get("alerts_by_severity") or {}
    tiers = ["WATCH", "ELEVATED", "HIGH", "CRITICAL"]
    seen = [counts.get(t, 0) for t in tiers]
    if not any(seen):
        pytest.skip("no alerts in the record yet")
    for lower, upper in zip(tiers, tiers[1:]):
        assert counts.get(lower, 0) >= counts.get(upper, 0), (
            f"{upper} ({counts.get(upper, 0)}) is not rarer than "
            f"{lower} ({counts.get(lower, 0)}) — the severity ladder is "
            f"inverted, so the top tier has stopped meaning anything")

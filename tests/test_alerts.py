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


def test_single_observation_cannot_reach_high():
    a = _a(z_score=5.0, rain_7d=2, rain_7d_anom=-25, persistence=0)
    assert SEVERITIES.index(a.severity) <= SEVERITIES.index("ELEVATED")


def test_low_quality_cannot_raise_an_alert():
    a = _a(z_score=6.0, rain_7d=1, rain_7d_anom=-30, persistence=5,
           quality="LOW_QUALITY")
    assert SEVERITIES.index(a.severity) <= SEVERITIES.index("WATCH")


def test_falling_index_is_never_an_alert():
    a = _a(indicator=0.02, z_score=-4.0, anomaly_flagged=True)
    assert a.severity == "NORMAL"


def test_critical_requires_extreme_deviation():
    corroborated = _a(z_score=3.0, rain_7d=2, rain_7d_anom=-25, persistence=4,
                      anomaly_flagged=True, upstream_id="P04", upstream_diff=0.08)
    assert corroborated.severity != "CRITICAL"
    extreme = _a(z_score=4.5, rain_7d=2, rain_7d_anom=-25, persistence=4,
                 anomaly_flagged=True, upstream_id="P04", upstream_diff=0.08)
    assert extreme.severity == "CRITICAL"


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

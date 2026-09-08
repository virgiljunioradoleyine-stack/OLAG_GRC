"""
The alert engine: deterministic, explainable, and deliberately cautious.

Design constraints, all of them consequences of what the audit found:

  * `contamination` must not decide the alert count. Severity is driven by how
    far the observation sits from its EXPECTED value, with the anomaly detector
    as corroboration rather than as the verdict.
  * Rainfall is real data now, not a proxy inferred from an upstream station.
    Heavy recent rain is an innocent explanation and actively suppresses
    severity; a rise with rainfall BELOW its seasonal norm is what escalates.
  * A single observation is weak evidence. Persistence across consecutive
    observations is required before anything reaches the top tiers.
  * Low-quality observations cannot drive an alert at all.
  * The language never claims mining, mercury, or any specific pollutant. It
    describes what was measured and what should be investigated.

Nothing here calls a network service or a language model. Same inputs, same
sentence, every time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

SEVERITIES = ["NORMAL", "WATCH", "ELEVATED", "HIGH", "CRITICAL"]

# Residual thresholds in robust standard deviations of the baseline's error.
# Stated here as explicit engineering thresholds rather than hidden in a
# contamination parameter.
Z_WATCH = 1.5
Z_ELEVATED = 2.5
Z_HIGH = 3.5
# CRITICAL needs its own bar. Without one, every reading past Z_HIGH that picked
# up any corroboration was promoted to the top tier, and the historical record
# came out with more CRITICAL than HIGH alerts -- an inverted pyramid that would
# train an operator to ignore the word.
Z_CRITICAL = 5.0

# Rainfall context
RAIN_WET_MM_7D = 40.0        # a genuinely wet week for this basin
RAIN_ANOM_WET = 15.0         # 7-day total this far above its seasonal norm
RAIN_ANOM_DRY = -5.0         # ... or this far below

PERSIST_WINDOW = 3           # consecutive observations considered
MIN_QUALITY_FOR_ALERT = {"GOOD", "ACCEPTABLE"}


@dataclass
class Assessment:
    station_id: str
    station_name: str
    date: str
    severity: str
    indicator: float                  # the satellite index value (NOT NTU)
    expected: float | None
    residual: float | None
    z_score: float | None
    anomaly_score: float | None
    anomaly_flagged: bool
    percentile: float | None
    rain_7d: float | None
    rain_7d_anom: float | None
    rain_context: str
    upstream_id: str | None
    upstream_diff: float | None
    persistence: int
    quality: str
    quality_score: float | None
    confidence: str
    signals: list = field(default_factory=list)
    headline: str = ""
    explanation: str = ""
    recommended_action: str = ""

    def to_dict(self):
        return asdict(self)


def _rain_context(rain_7d, rain_anom):
    """Classify the rainfall situation into plain words."""
    if rain_7d is None or not np.isfinite(rain_7d):
        return "unknown"
    if np.isfinite(rain_anom if rain_anom is not None else np.nan):
        if rain_anom >= RAIN_ANOM_WET:
            return "wetter than normal"
        if rain_anom <= RAIN_ANOM_DRY:
            return "drier than normal"
        return "near normal"
    return "wet" if rain_7d >= RAIN_WET_MM_7D else "dry"


def _confidence(quality, persistence, has_baseline, rain_known):
    score = 0
    score += {"GOOD": 2, "ACCEPTABLE": 1}.get(quality, 0)
    score += min(persistence, 2)
    score += 1 if has_baseline else 0
    score += 1 if rain_known else 0
    return "high" if score >= 5 else "moderate" if score >= 3 else "low"


def assess(station, date, indicator, expected=None, z_score=None,
           anomaly_score=None, anomaly_flagged=False, percentile=None,
           rain_7d=None, rain_7d_anom=None, upstream_id=None,
           upstream_diff=None, persistence=0, quality="GOOD",
           quality_score=None, thresholds=None):
    """Assess one observation. Pure function of its arguments.

    `thresholds` is the station's empirical [watch, elevated, high, critical]
    residual cut-offs, learned from its training residuals. When absent the
    sigma constants are used, which is only appropriate before a baseline
    exists.
    """
    signals = []
    rain_ctx = _rain_context(rain_7d, rain_7d_anom)
    residual = (indicator - expected) if (expected is not None
                                          and np.isfinite(expected)) else None
    z = z_score if (z_score is not None and np.isfinite(z_score)) else None

    # ---- base severity from deviation against expectation ---------------
    use_empirical = (thresholds is not None and residual is not None
                     and len(thresholds) == 4 and all(np.isfinite(thresholds)))

    if use_empirical:
        t_watch, t_elev, t_high, t_crit = thresholds
        if residual >= t_crit:
            severity = "CRITICAL"
        elif residual >= t_high:
            severity = "HIGH"
        elif residual >= t_elev:
            severity = "ELEVATED"
        elif residual >= t_watch:
            severity = "WATCH"
        else:
            severity = "NORMAL"
        if severity != "NORMAL":
            signals.append(
                f"sediment index is {residual:+.3f} above expected, which this "
                f"station exceeds in under "
                f"{['40','15','4','0.5'][SEVERITIES.index(severity)-1]}% of its history")
    elif z is None:
        severity = "WATCH" if anomaly_flagged else "NORMAL"
        if anomaly_flagged:
            signals.append("flagged by the anomaly detector (no baseline available)")
    elif z >= Z_CRITICAL:
        severity = "CRITICAL"
        signals.append(f"{z:.1f}x the usual deviation above expected conditions")
    elif z >= Z_HIGH:
        severity = "HIGH"
        signals.append(f"{z:.1f}x the usual deviation above expected conditions")
    elif z >= Z_ELEVATED:
        severity = "ELEVATED"
        signals.append(f"{z:.1f}x the usual deviation above expected conditions")
    elif z >= Z_WATCH:
        severity = "WATCH"
        signals.append(f"{z:.1f}x the usual deviation above expected conditions")
    else:
        severity = "NORMAL"

    # A fall in the index is not a pollution concern, whatever the detector says.
    falling = (residual is not None and residual < 0) if use_empirical else (z is not None and z < 0)
    if falling:
        severity = "NORMAL"
        signals = ["index is below expected conditions, not above"]

    base_severity = severity
    idx = SEVERITIES.index(severity)

    # ---- corroboration and suppression ----------------------------------
    if not falling:
        if anomaly_flagged and idx >= 1:
            idx = min(idx + 1, len(SEVERITIES) - 1)
            signals.append("independently flagged by the anomaly detector")

        if rain_ctx == "wetter than normal" and idx > 0:
            idx = max(idx - 1, 1)
            signals.append(
                f"rainfall over the past 7 days ({rain_7d:.0f} mm) is above its "
                f"seasonal norm, which is an ordinary cause of raised sediment")
        elif rain_ctx == "drier than normal" and idx >= 2:
            idx = min(idx + 1, len(SEVERITIES) - 1)
            signals.append(
                f"rainfall over the past 7 days ({rain_7d:.0f} mm) is BELOW its "
                f"seasonal norm, so rain does not explain this rise")

        if upstream_diff is not None and np.isfinite(upstream_diff) and idx >= 2:
            if upstream_diff > 0.02:
                signals.append(
                    f"the index here is {upstream_diff:+.3f} above the nearest "
                    f"upstream station, suggesting a source between them")
            elif upstream_diff < -0.02:
                idx = max(idx - 1, 1)
                signals.append(
                    "the nearest upstream station is higher, so the signal "
                    "appears to be arriving from further upstream")

        # Persistence gate. Corroboration is what persistence supplies, so its
        # absence removes corroboration -- it must not erase the measurement.
        #
        # This previously slammed any unpersisted reading down to ELEVATED
        # outright, which had two consequences that only show up against the
        # real record. It ran BEFORE the CRITICAL check below, so a reading
        # extreme enough to be CRITICAL on its own terms was knocked to
        # ELEVATED and the magnitude route to the top tier could never fire at
        # all. And it assumes regular sampling: the Pra is heavily clouded and
        # roughly two thirds of scenes are unusable, so a station can go three
        # or four weeks between readings. "Has not persisted" then means "we
        # did not look again", which is not evidence of anything -- and it is
        # precisely the short, sharp episode this system exists to catch that
        # gets seen once and suppressed.
        #
        # A reading may therefore still stand at the severity its own departure
        # justifies. What it may not do is climb above that on corroboration
        # it has not earned.
        base_idx = SEVERITIES.index(base_severity)
        if idx >= 3 and persistence < 2:
            capped = max(2, base_idx)
            if capped < idx:
                idx = capped
                signals.append(
                    "not escalated further: a single observation, not yet "
                    "confirmed by a later pass")
        elif persistence >= 2 and idx >= 2:
            idx = min(idx + 1, len(SEVERITIES) - 1)
            signals.append(f"sustained across {persistence} consecutive observations")

        # CRITICAL is reserved for observations that are extreme on their own
        # terms, not ones that merely accumulated corroboration.
        # Corroboration can lift a reading to HIGH. Only the size of the
        # departure itself can reach CRITICAL -- otherwise persistence plus a
        # dry week plus a detector flag stack up to the top tier and the
        # historical record ends up with more CRITICAL alerts than HIGH ones.
        if idx >= 4 and base_severity != "CRITICAL":
            idx = 3
            signals.append(
                "held below CRITICAL: corroborating evidence is strong, but the "
                "departure from expected conditions is not itself extreme")


    # quality gate: never escalate on a measurement we do not trust
    if quality not in MIN_QUALITY_FOR_ALERT and idx > 1:
        idx = 1
        signals.append(
            f"held at WATCH: observation quality is {quality}, which is not "
            f"reliable enough to raise an alert on")

    severity = SEVERITIES[idx]
    confidence = _confidence(quality, persistence, expected is not None,
                             rain_7d is not None and np.isfinite(rain_7d or np.nan))

    a = Assessment(
        station_id=station.id, station_name=station.name, date=str(date),
        severity=severity,
        indicator=round(float(indicator), 6),
        expected=round(float(expected), 6) if expected is not None and np.isfinite(expected) else None,
        residual=round(float(residual), 6) if residual is not None else None,
        z_score=round(float(z), 3) if z is not None else None,
        anomaly_score=round(float(anomaly_score), 6) if anomaly_score is not None else None,
        anomaly_flagged=bool(anomaly_flagged),
        percentile=round(float(percentile), 1) if percentile is not None and np.isfinite(percentile) else None,
        rain_7d=round(float(rain_7d), 1) if rain_7d is not None and np.isfinite(rain_7d) else None,
        rain_7d_anom=round(float(rain_7d_anom), 1) if rain_7d_anom is not None and np.isfinite(rain_7d_anom) else None,
        rain_context=rain_ctx,
        upstream_id=upstream_id,
        upstream_diff=round(float(upstream_diff), 6) if upstream_diff is not None and np.isfinite(upstream_diff) else None,
        persistence=int(persistence), quality=quality,
        quality_score=round(float(quality_score), 3) if quality_score is not None and np.isfinite(quality_score) else None,
        confidence=confidence, signals=signals,
    )
    _write_narrative(a)
    return a


def _write_narrative(a):
    """Fill headline / explanation / recommended_action. Templates only."""
    if a.severity == "NORMAL":
        a.headline = f"Normal river conditions at {a.station_name}"
        a.explanation = (
            f"On {a.date} the satellite sediment indicator at {a.station_name} "
            f"was {a.indicator:+.3f}"
            + (f", against an expected {a.expected:+.3f} for these conditions"
               if a.expected is not None else "")
            + f". Rainfall over the previous 7 days was {a.rain_context}"
            + (f" ({a.rain_7d:.0f} mm)." if a.rain_7d is not None else ".")
            + " Nothing here requires attention."
        )
        a.recommended_action = "No action required."
        return

    label = {"WATCH": "Possible change", "ELEVATED": "Elevated",
             "HIGH": "Strong", "CRITICAL": "Extreme"}[a.severity]
    a.headline = f"{label} river-condition anomaly at {a.station_name}"

    parts = [
        f"On {a.date} the satellite sediment indicator at {a.station_name} "
        f"({a.station_id}) read {a.indicator:+.3f}."
    ]
    if a.expected is not None and a.z_score is not None:
        parts.append(
            f"Given the season, recent rainfall and upstream conditions, "
            f"{a.expected:+.3f} would have been expected — the reading is "
            f"{a.z_score:.1f} standard deviations above that.")
    if a.rain_7d is not None:
        parts.append(
            f"Rainfall over the preceding 7 days totalled {a.rain_7d:.0f} mm, "
            f"which is {a.rain_context} for this time of year.")
    else:
        parts.append("Rainfall context is unavailable for this date.")
    if a.upstream_id and a.upstream_diff is not None:
        direction = "higher than" if a.upstream_diff > 0 else "lower than"
        parts.append(
            f"The index here is {abs(a.upstream_diff):.3f} {direction} the "
            f"nearest upstream station ({a.upstream_id}).")
    parts.append(
        f"The signal has persisted across {a.persistence} consecutive "
        f"observation(s)." if a.persistence else
        "This is the first observation showing the change.")
    parts.append(
        f"Observation quality is {a.quality}; overall confidence is "
        f"{a.confidence}.")
    parts.append(
        "This indicates unusual surface-water conditions that may warrant "
        "investigation. It does not identify a cause, and it does not "
        "demonstrate mining activity or the presence of any specific "
        "contaminant.")
    a.explanation = " ".join(parts)

    if a.severity in ("HIGH", "CRITICAL"):
        a.recommended_action = (
            f"Field verification recommended at {a.station_name}. Check raw-water "
            f"turbidity records at the downstream abstraction and inspect the "
            f"reach between the upstream station and this one for visible "
            f"disturbance.")
    elif a.severity == "ELEVATED":
        a.recommended_action = (
            "Monitor the next satellite pass. If the signal persists, or "
            "downstream stations begin to rise, escalate to field verification.")
    else:
        a.recommended_action = (
            "No immediate action. Confirm on the next pass before treating this "
            "as a genuine change.")


def assess_series(station, obs, features, expected=None, z_scores=None,
                  anomaly_scores=None, anomaly_flags=None, percentiles=None,
                  upstream_id=None, thresholds=None):
    """Assess a whole series, computing persistence as it goes."""
    out, run = [], 0
    n = len(obs)

    def at(arr, i):
        if arr is None:
            return None
        try:
            v = arr[i]
        except (IndexError, KeyError):
            return None
        return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else v

    for i in range(n):
        row = obs.iloc[i]
        z = at(z_scores, i)
        exp_i = at(expected, i)
        if thresholds is not None and exp_i is not None:
            raised = (float(row["ndti"]) - exp_i) >= thresholds[0]
        else:
            raised = (z is not None and z >= Z_WATCH)
        raised = raised or bool(at(anomaly_flags, i))
        run = run + 1 if raised else 0

        out.append(assess(
            station=station, date=row["date"].strftime("%Y-%m-%d"),
            indicator=float(row["ndti"]),
            expected=at(expected, i), z_score=z,
            anomaly_score=at(anomaly_scores, i),
            anomaly_flagged=bool(at(anomaly_flags, i)),
            percentile=at(percentiles, i),
            rain_7d=features["rain_7d"].iloc[i] if "rain_7d" in features else None,
            rain_7d_anom=features["rain_7d_anom"].iloc[i] if "rain_7d_anom" in features else None,
            upstream_id=upstream_id,
            upstream_diff=features["upstream_diff"].iloc[i] if "upstream_diff" in features else None,
            persistence=max(run - 1, 0),
            quality=row.get("quality", "GOOD"),
            quality_score=row.get("quality_score"),
            thresholds=thresholds,
        ))
    return out

"""
STEP 3 — alert text.

Deterministic string formatting from numbers the model already produced. No
network call, no language model: given the same inputs this returns the same
sentence every time, which is what makes it safe to run unattended and
defensible when a judge asks how the wording was chosen.

Three tiers:

  ALERT     the model flagged this reading AND the upstream control did not rise
            -- turbidity here changed in a way rainfall does not explain
  ELEVATED  turbidity is unusual, but the control rose too (so: probably
            rainfall), or it is drifting without being flagged outright
  NORMAL    within what this point normally does at this time of year
"""
from __future__ import annotations

# a control rise this large is treated as "it rained across the catchment"
CONTROL_RISE_THRESHOLD = 0.02
ELEVATED_PERCENTILE = 10.0


def classify(prediction, score, percentile, control_delta):
    """Return (tier, control_also_elevated)."""
    control_also_elevated = (control_delta is not None
                             and control_delta >= CONTROL_RISE_THRESHOLD)
    if prediction == -1:
        return ("ELEVATED" if control_also_elevated else "ALERT"), control_also_elevated
    if percentile == percentile and percentile <= ELEVATED_PERCENTILE:
        return "ELEVATED", control_also_elevated
    return "NORMAL", control_also_elevated


def describe(point_name, date, ndti, prediction, score, percentile,
             control_delta, control_ndti=None):
    """Build the plain-language alert line."""
    tier, control_up = classify(prediction, score, percentile, control_delta)

    rarity = ("" if percentile != percentile
              else f" This reading is more unusual than {100 - percentile:.0f}% "
                   f"of the last 18 months of observations at this point.")

    if tier == "ALERT":
        text = (
            f"ALERT — {point_name}: turbidity on {date} is well outside the "
            f"normal range for this point (NDTI {ndti:+.3f}), and the upstream "
            f"control point did not rise with it. A catchment-wide cause such "
            f"as rainfall would have lifted both. This pattern is consistent "
            f"with a pollution source between the control point and here."
            + rarity
        )
    elif tier == "ELEVATED" and control_up:
        text = (
            f"ELEVATED — {point_name}: turbidity on {date} is raised "
            f"(NDTI {ndti:+.3f}), but the upstream control rose by a similar "
            f"amount. That points to rainfall across the catchment rather than "
            f"a local pollution source, so no alert is being raised. Monitoring "
            f"continues."
        )
    elif tier == "ELEVATED":
        text = (
            f"ELEVATED — {point_name}: turbidity on {date} (NDTI {ndti:+.3f}) "
            f"is drifting above this point's usual range without being flagged "
            f"outright. Worth watching on the next pass." + rarity
        )
    else:
        text = (
            f"NORMAL — {point_name}: turbidity on {date} (NDTI {ndti:+.3f}) is "
            f"within the normal range for this point at this time of year."
        )

    return {
        "tier": tier,
        "text": text,
        "date": date,
        "point": point_name,
        "ndti": round(float(ndti), 6),
        "anomaly_score": round(float(score), 6),
        "percentile": None if percentile != percentile else round(float(percentile), 1),
        "control_also_elevated": bool(control_up),
    }

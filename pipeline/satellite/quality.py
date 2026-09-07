"""
Per-observation data quality.

The audit found readings built from 4 water pixels being treated as
interchangeable with readings built from 748. They are not. A 4-pixel median is
dominated by noise, and letting one drive an alert is how a monitoring system
loses its credibility. Every observation now carries an explicit quality level,
and the alert engine refuses to escalate on anything below ACCEPTABLE.
"""
from __future__ import annotations

QUALITY_LEVELS = ["GOOD", "ACCEPTABLE", "LOW_QUALITY", "REJECTED"]

# Thresholds are engineering judgements, stated here rather than buried:
#  - a 1 km reach yields several hundred pixels when the view is clear
#  - below ~40 the median starts swinging on individual mixed pixels
#  - below 10 it is not a measurement of the river, it is a measurement of noise
GOOD_PIXELS = 150
ACCEPTABLE_PIXELS = 40
MIN_PIXELS = 10

# Spatial scatter within the reach. High scatter means the window is not seeing
# one coherent water body -- cloud edge, shadow, or a mixed bank.
GOOD_STD = 0.06
ACCEPTABLE_STD = 0.12

# Fraction of the reach rejected as cloud/shadow by SCL.
#
# Calibrated against the collected record rather than guessed: 70% of real
# observations have more than 20% of the reach clouded, which is simply what the
# Pra basin looks like. More importantly, cloud fraction is the wrong primary
# gate. If 80% of the reach is under cloud but the clear fifth still yields 300
# water pixels, that is a perfectly good measurement of the river -- the pixel
# count already captures whether we saw enough water. Cloud fraction is retained
# because a heavily obscured reach may be sampling an unrepresentative part of
# the channel, but it is a secondary signal and weighted accordingly.
GOOD_CLOUD = 0.50
ACCEPTABLE_CLOUD = 0.85


def quality_of(water_pixels, ndti_std, cloud_fraction):
    """Return (level, score 0-1, reasons[]).

    The score is a continuous companion to the level, used for weighting rather
    than gating, so a GOOD observation with 600 pixels can outweigh a GOOD one
    with 160 without needing another category.
    """
    reasons = []

    if water_pixels is None or water_pixels < MIN_PIXELS:
        return "REJECTED", 0.0, [f"only {water_pixels} water pixels (min {MIN_PIXELS})"]

    if water_pixels >= GOOD_PIXELS:
        px_level, px_score = 0, 1.0
    elif water_pixels >= ACCEPTABLE_PIXELS:
        px_level, px_score = 1, 0.6
        reasons.append(f"{water_pixels} water pixels (below {GOOD_PIXELS})")
    else:
        px_level, px_score = 2, 0.3
        reasons.append(f"only {water_pixels} water pixels")

    std = float(ndti_std) if ndti_std is not None and ndti_std == ndti_std else 0.0
    if std <= GOOD_STD:
        std_level, std_score = 0, 1.0
    elif std <= ACCEPTABLE_STD:
        std_level, std_score = 1, 0.6
        reasons.append(f"spatial scatter {std:.3f}")
    else:
        std_level, std_score = 2, 0.2
        reasons.append(f"high spatial scatter {std:.3f}")

    cf = float(cloud_fraction) if cloud_fraction is not None and cloud_fraction == cloud_fraction else 0.0
    if cf <= GOOD_CLOUD:
        cl_level, cl_score = 0, 1.0
    elif cf <= ACCEPTABLE_CLOUD:
        cl_level, cl_score = 1, 0.6
        reasons.append(f"{cf:.0%} of window cloud-masked")
    else:
        cl_level, cl_score = 2, 0.2
        reasons.append(f"{cf:.0%} of window cloud-masked")

    worst = max(px_level, std_level, cl_level)
    level = ["GOOD", "ACCEPTABLE", "LOW_QUALITY"][worst]
    score = round(px_score * 0.5 + std_score * 0.3 + cl_score * 0.2, 3)
    return level, score, reasons

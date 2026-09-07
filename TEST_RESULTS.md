# TEST_RESULTS

Every number here was measured against the collected historical record
(2017-01-01 → 2026-09-07). Failures are reported alongside successes; the most
important result in this document is a **miss**.

| Point | Readings | Span | ALERT | ELEVATED | NORMAL |
|---|---|---|---|---|---|
| control | 207 | 2017-01-07 → 2026-06-19 | — | — | — |
| monitor | 260 | 2017-01-27 → 2026-08-20 | 4 | 8 | 248 |
| intake | 200 | 2017-01-27 → 2026-08-20 | 1 | 6 | 193 |

Model: Isolation Forest, 200 trees, contamination 0.05, 7 features.

---

## 1. Historical event replay — THE MODEL MISSED THE EVENT

We found one precisely dated, independently reported incident to test against.
On **14 August 2026** raw-water turbidity at the Daboase intake reached
**11,955 NTU** against a permitted limit of 500 NTU — roughly 24× over limit,
reported as a galamsey-driven pollution event threatening plant shutdown.

Our two nearest readings, four and six days later:

| Date | NDTI | Model verdict | Score percentile |
|---|---|---|---|
| 2026-08-18 | +0.1135 | **NORMAL** | 95.0 (i.e. very ordinary) |
| 2026-08-20 | +0.1162 | **NORMAL** | 95.5 |

**The system would not have warned anyone.** Worse, it scored the event as more
ordinary than 95% of its training data. Three separate causes, all real:

### (a) NDTI is insensitive at high sediment loads

NDTI is a *normalized* index: `(red − green) / (red + green)`. When sediment
load rises far enough, both bands brighten together and the ratio barely moves —
the normalization cancels exactly the signal we want. Reading the raw bands at
the intake shows how badly:

| Date | NDTI | red | green | Note |
|---|---|---|---|---|
| 2026-08-18 | +0.1135 | **0.3910** | 0.3104 | documented 11,955 NTU event |
| 2026-08-20 | +0.1162 | **0.3704** | 0.2936 | " |
| 2026-06-01 | +0.0979 | 0.3678 | 0.3010 | ordinary |
| 2025-02-04 | +0.2306 | 0.1886 | 0.1188 | flagged ELEVATED |
| 2020-01-27 | +0.2022 | 0.2150 | 0.1413 | flagged ELEVATED |

Red reflectance on the event dates is **0.37–0.39, nearly double** the 0.19–0.22
seen on the dates NDTI scored as most turbid — while NDTI ran in the *opposite*
direction, falling from 0.23 to 0.12. The index we chose ranks the worst
recorded pollution event as calmer than a routine January.

The caveat that keeps this honest: absolute reflectance also rises with
atmospheric haze, which is precisely why a normalized index was chosen in the
first place. So the answer is not to discard NDTI but to give the model both,
and let the control point reject the common-mode atmospheric component. That
change requires re-collecting the archive with the raw bands stored; `fetch.py`
now records `red` and `green` per reading so the next collection captures them.

### (b) The control point goes blind in the rainy season

Control readings falling in July–September, by year:

```
2017: 4    2018: 5    2019: 1    2020: 3    2021: 6
2022: 1    2023: 0    2024: 0    2025: 0    2026: 0
```

The control's most recent reading of any kind is **19 June 2026**. For the August
event there was no control reading within the 10-day matching window, so
`control_ndti` fell back to the point's own baseline and `control_delta` was
0.0000 — the control-suppression feature was **inert on the one date it mattered
most**. Galamsey turbidity peaks in the rainy season; so does the cloud that
blinds the control point. The upper-basin site (T30NXM) is materially cloudier
than the two downstream sites.

### (c) Six-day latency

Sentinel-2 revisit plus cloud meant the nearest usable observations were 4 and 6
days after the event. For a plant that needs hours of warning, a 5-day mean
revisit is a structural ceiling on this approach, independent of the model.

**Verdict: the replay test fails.** The pipeline, the mask, the model and the
alert logic all work as designed; the *measurement* does not carry the signal.

## 2. Control-suppression test — PASSES

The control logic works, and demonstrably prevents false alarms. Five historical
readings were flagged by the model as anomalous **and** rising, but were held at
ELEVATED rather than escalated to ALERT because the upstream control rose too:

| Point | Date | NDTI | Δ here | Δ control | Result |
|---|---|---|---|---|---|
| monitor | 2020-01-27 | +0.2135 | +0.0827 | +0.1004 | suppressed |
| monitor | 2022-01-26 | +0.1918 | +0.0491 | +0.0375 | suppressed |
| intake | 2020-01-27 | +0.2022 | +0.1452 | +0.1004 | suppressed |
| intake | 2025-02-04 | +0.2306 | +0.1144 | +0.0714 | suppressed |
| intake | 2026-01-25 | +0.1824 | +0.0657 | +0.0233 | suppressed |

2020-01-27 is the clearest case: both downstream points spiked hard on the same
date, and so did the upstream control. A catchment-wide rise is weather, not
mining, and the system correctly declined to cry wolf at both points at once.

Two caveats, and the second is severe. First, this test rests on the control
point *having* a reading, and per §1(b) it frequently does not. Second — see §6 —
the control and the monitored points only move in the same direction on ~52% of
dates, which is a coin flip. With agreement that weak, roughly half of any set of
spikes will show the control rising by chance alone. **These five suppressions
may be coincidence rather than the logic working.** They are reported here
because they are what the system did, not as evidence that it reasoned correctly.

## 3. False-positive rate — PASSES

Three quiet three-month windows with no reported incident:

| Window | monitor | intake |
|---|---|---|
| 2019-04-01 → 2019-06-30 | 0 ALERT / 4 readings | 0 / 5 |
| 2022-03-01 → 2022-05-31 | 0 / 3 | 0 / 2 |
| 2024-04-01 → 2024-06-30 | 0 / 4 | 0 / 6 |

**0 false alerts in 24 readings.** Across the whole record the rate is 4 alerts
in 260 readings (monitor, 0.4/year) and 1 in 200 (intake, 0.1/year).

The honest reading of this: a low false-positive rate is easy to achieve by
being insensitive, and §1 shows we *are* insensitive. This result should not be
quoted without §1 beside it.

## 4. Contamination choice — 0.05

Alerts are counted after the direction filter (a flagged reading whose turbidity
*fell* is not a pollution event):

| Contamination | monitor flagged | → ALERTs | intake flagged | → ALERTs |
|---|---|---|---|---|
| 0.02 | 6 (2%) | 1 (0.1/yr) | 4 (2%) | 1 (0.1/yr) |
| **0.05** | **13 (5%)** | **4 (0.4/yr)** | **10 (5%)** | **1 (0.1/yr)** |
| 0.10 | 26 (10%) | 7 (0.7/yr) | 20 (10%) | 2 (0.2/yr) |

**0.05 chosen.** At 0.02 the system fires roughly once a decade per point, which
is not an early-warning system. At 0.10 the additional flags are weak — several
sit at low absolute turbidity (2021-07-10 at NDTI +0.039, 2024-01-21 at +0.057),
so they are unusual only in shape, not severity. The four alerts at 0.05 all
show turbidity rising here while the control fell (control Δ between −0.11 and
−0.18): the cleanest possible form of the signal.

Flagged dates at 0.05 that became ALERTs (monitor): 2018-08-05, 2020-12-27,
2023-10-18, 2023-12-02. Intake: 2018-08-15.

## 5. Direction filtering — a finding worth recording

An Isolation Forest flags anything unusual in *either* direction, and on this
record **more than half of all flags were turbidity falling, not rising** — the
river becoming unusually clean. At contamination 0.05 the monitor point had 13
flags, of which 10 had a flat control, of which only **4** were rises.

Unusually clean water is not a reason to warn a treatment plant, so the alert
rules now require a rise before escalating. Without that filter the system would
have produced more than twice as many alerts, most of them for good news.

## 6. Is the control point valid? — the premise does not hold in our data

The control's entire job rests on one assumption: **when it rains across the
catchment, all three points rise together**. If that is true, their date-to-date
changes should correlate strongly. We tested it.

**Siting first.** Confirmed on OpenStreetMap: the control sits on the **Pra
mainstem**, and imagery puts it **above** the Pra/Offin confluence — the channel
is 40 m wide at the point and 120 m wide below the junction 8 km south-west. The
Offin is the heavily mined tributary, so this is the right side of the junction.
Siting is not the problem.

**But the correlation is not there.** Matching readings by nearest date:

| Pair | n (same day) | r (NDTI level) | r (NDTI *change*) | move same direction |
|---|---|---|---|---|
| control ↔ monitor | 138 | +0.34 | **+0.25** | **53%** |
| control ↔ intake | 108 | +0.39 | **+0.20** | **52%** |
| monitor ↔ intake | 135 | +0.39 | **+0.28** | **57%** |

Direction agreement of ~52% is a coin flip. Tightening the match from 10 days to
same-day helps the level correlation but not the direction agreement at all.

**The sanity check is what makes this interpretable.** `monitor` and `intake` sit
on the *same river*, 22 km apart, read from the *same tile* on the *same dates* —
and they agree barely better (r = 0.28, 57%) than the control does. So the weak
correlation is **not** a badly sited control. Every pair of points behaves this
way, which points at the measurement rather than the geography.

**The measurement is noise-dominated.** Comparing readings taken close together
in time (when the river genuinely cannot have changed much) against readings far
apart:

| Point | median \|ΔNDTI\|, readings ≤3 days apart | ≥20 days apart | implied noise share |
|---|---|---|---|
| monitor | 0.0434 (n=7) | 0.0543 (n=57) | **~80%** |
| intake | 0.0177 (n=6) | 0.0374 (n=53) | ~47% |

For the monitor point, roughly **four fifths of the apparent change between
readings is measurement noise**, not river. (The ≤3-day samples are small — 7 and
6 pairs — so treat these as indicative, not precise.) Within-scene pixel scatter
alone is 0.020–0.030 NDTI against a total date-to-date spread of 0.052–0.061.

**What this means.** The control-suppression logic is not wrong in principle, but
in this data the shared rainfall signal it depends on is buried under noise. We
should not claim to a judge that the control demonstrably prevents false alarms —
we can only claim it is designed to, and that the data so far cannot confirm it.

The fixes are the same ones §1 already points at, which is reassuring: more
pixels per reading (sample a length of channel rather than a 100 m box),
absolute reflectance rather than a normalised index, and temporal smoothing
before comparing points.

## 7. Galamsey upstream of the control — present, growth unproven

True-colour imagery shows extensive bare, blotchy ground and stripped riverbed on
the Pra immediately upstream of the control point (`docs/`). Visually it appears
to expand between 2017 and 2026.

We tried to prove that growth by measuring bare bright ground (NDVI < 0.25,
red > 0.12) in the same 4 × 4 km reach on the clearest dry-season scene each year:

```
2017  88 ha    2020  80 ha    2023   99 ha    2025  39 ha
2018  50 ha    2021  84 ha    2024  131 ha    2026  114 ha
```

88 ha → 114 ha is a 1.3× increase, but the scatter between years is as large as
the trend (39 ha in 2025). The measure is confounded by *when* in the dry season
each scene falls — vegetation greenness and exposed riverbed both shift by weeks.
**We cannot claim from this that mining upstream of the control is growing.**
What we can say is that ~5–8% of that reach is stripped ground in every year
measured, directly on the channel. The control point is not in pristine
catchment, and its median NDTI (+0.0855) is not much cleaner than the intake's
(+0.0981).

---

## What we would fix next, in priority order

1. **Add absolute red reflectance as a feature** (§1a). The single change most
   likely to convert the missed event into a detection. `fetch.py` now records
   the raw bands; needs an archive re-collection.
2. **Replace or supplement the control point** (§1b). A control that is blind
   for four consecutive rainy seasons cannot do its job. Options: a control in a
   less cloudy part of the basin, relaxing the 10-day control-matching window,
   or a seasonal climatological baseline as fallback when no control reading
   exists.
3. **Validate against a turbidity record.** GWCL publishes NTU readings at
   Daboase. Even a handful of dated NTU values would let us calibrate NDTI (and
   red reflectance) against ground truth instead of inferring sensitivity from
   one event.
4. **Raise the signal-to-noise ratio** (§6). Sample a length of river channel
   rather than a 100 m square — more pixels per reading averages the noise down —
   and smooth over time before comparing points. Until this improves, the control
   logic cannot be shown to work.
5. **Be honest about latency** (§1c). This system's realistic claim is
   *"detects multi-day pollution episodes and trends"*, not *"warns hours before
   a slug arrives"*. The competition entry should say so.

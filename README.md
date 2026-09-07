# Pra River Watch

**Early warning for unusual river and sediment conditions in Ghana's Pra basin.**

Dashboard: https://olag-grc-viradotech.vercel.app

Illegal gold mining fills the Pra with sediment. When a pollution slug reaches
the Ghana Water Company abstraction at Daboase, the plant cannot treat the water
and supply to Sekondi-Takoradi stops — with no warning. Pra River Watch measures
a satellite-derived sediment index at eight points along the river, learns what
is normal for each point given the season and the rainfall, and flags departures
that rainfall does not explain.

> ### Scientific disclaimer
>
> This system detects **unusual satellite-observed river conditions** and
> provides early warnings for investigation. It does **not** independently prove
> the presence of illegal mining, and it does **not** identify specific chemical
> contaminants such as mercury or arsenic.
>
> No in-situ water-quality measurements were obtainable for this basin, so the
> index is **not calibrated to NTU or TSS** and is never reported as such. It is
> published as a **Sediment Anomaly Index**. See [Ground truth](#ground-truth).

---

## Architecture

```
 Public data (no accounts, no API keys)
   Sentinel-2 L2A COGs ──┐
   NASA POWER rainfall ──┤
   OpenStreetMap rivers ─┘
            │
            ▼
   GitHub Actions  ── pipeline.yml (every 3 days)
            │          acquire → validate → features → score → alerts → export
            │        train.yml (monthly, gated on validation)
            ▼
   Versioned CSV/JSON committed to the repository
            │
            ▼
   Vercel ── Next.js dashboard reading the exported JSON
```

No database server, no VPS, no paid service. GitHub holds the data, Actions runs
the pipeline, Vercel serves the dashboard.

## Data sources

Every source is anonymous — no account, no API key. Reachability was verified
from CI, and the evidence is committed at `data/sources/probe_evidence.json`.

| Dataset | Purpose | Access | Auth | Licence |
|---|---|---|---|---|
| [Sentinel-2 L2A COGs](https://registry.opendata.aws/sentinel-2-l2a-cogs/) | Surface reflectance (B03, B04, B08, B11, SCL) | S3 listing + HTTP range reads on `sentinel-cogs.s3.us-west-2.amazonaws.com` | None | Copernicus open |
| [NASA POWER](https://power.larc.nasa.gov/) | Daily rainfall, primary | JSON point API | None | Open |
| [Open-Meteo ERA5](https://open-meteo.com/en/docs/historical-weather-api) | Daily rainfall, fallback | JSON archive API | None | CC-BY-4.0 |
| [OpenStreetMap / Overpass](https://overpass-api.de/) | River centreline, place names | Overpass QL | None | ODbL |
| [Esri World Imagery](https://www.arcgis.com/) / [OSM tiles](https://www.openstreetmap.org/) | Basemaps | XYZ tiles | None | See `LICENSE` |

**Investigated and unavailable** — documented rather than quietly dropped:

- **HydroRIVERS / HydroSHEDS** — the better hydrographic product, but
  `data.hydrosheds.org` sits behind a Cloudflare interstitial and returns 403 to
  any non-browser client. OpenStreetMap is used instead.
- **CHIRPS** — reachable, but distributed as one continental GeoTIFF per day.
  Far too heavy for a CI job when a point API gives the same quantity.
- **data.gov.gh** — connection refused; the portal appears offline.
- **GEMStat (UNEP)** — portal loads, but data requires a manual request form.

## Ground truth

**There is none, and that shapes everything.** We searched for an anonymous,
programmatic source of Ghanaian in-situ water-quality data and found no such
thing. Consequently:

- The system reports a **Sediment Anomaly Index**, never NTU.
- No supervised turbidity model exists (Model C below is implemented but
  untrained, because training it would require inventing labels).
- Evaluation reports what can honestly be measured: how well the
  expected-condition model generalises to unseen periods, not accuracy against
  a measurement that does not exist.

`data/groundtruth/README.md` documents the CSV schema. Drop real measurements in
and supervised calibration becomes trainable automatically. A test fails loudly
if rows appear, so the "no ground truth" claim cannot silently go stale.

## Monitoring network

Eight stations, ordered upstream → downstream, defined in `pipeline/config.py`.
The network is data-driven; adding a station requires no code change. Every
coordinate was verified to sit on the channel against Sentinel-2 persistent-water
masks (`scripts/verify_point.py`) — the coordinates in the original project brief
were all off-channel.

| ID | Name | Role | Coordinates |
|---|---|---|---|
| P01 | Pra Upper Basin | control | 5.875062, −1.522239 |
| P02 | Pra Mid-Upper Reach | monitor | 5.711454, −1.588530 |
| P03 | Pra at Beposo Reach | monitor | 5.423526, −1.628935 |
| P04 | Pra Mid-Lower Reach | monitor | 5.345347, −1.620784 |
| P05 | Daboase Intake (GWCL) | intake | 5.230010, −1.569200 |
| P06 | Pra Lower Reach | downstream | 5.145801, −1.653094 |
| P07 | Pra Lower Reach South | downstream | 5.137311, −1.648116 |
| P08 | Pra Estuary Approach | downstream | 5.109413, −1.614529 |

## Method

**1 · Observation.** Only a ~1 km reach around each station is read, using COG
range requests, so a 240 MB scene is never downloaded. Scenes are read once per
tile and shared across every station in it.

**2 · Water.** A persistent-water mask built from MNDWI across many clear dates,
restricted to the connected channel the station sits on. MNDWI rather than the
SCL water class: sediment-laden water is spectrally close to bare soil, so the
standard water class is blind to exactly the condition we measure.

**3 · Quality.** Every observation carries GOOD / ACCEPTABLE / LOW_QUALITY, from
water-pixel count, spatial scatter and cloud fraction. Thresholds are calibrated
against the real record. A low-quality observation cannot raise an alert.

**4 · Features (40).** Spectral, temporal, seasonal (cyclical sin/cos),
rainfall (1/3/7/14/30-day totals and anomalies), spatial (upstream and control
comparison, along-river distance), and quality. All strictly backward-looking.

**5 · Models.**
- *Model A — anomaly:* Isolation Forest. `contamination` no longer decides the
  alert count; the operating threshold is calibrated on held-out validation data.
- *Model B — expected conditions:* HistGradientBoosting predicts what the index
  *should* be given season, rainfall and upstream state. The residual is what the
  alert engine reasons about, scored against a naive 30-day-mean reference.
- *Model C — supervised calibration:* implemented, untrained, awaiting ground
  truth.

**6 · Validation.** Chronological only, never shuffled. Train ≤ 2023,
validate 2024, test 2025+. Preprocessing is fitted on training rows alone.

**7 · Alerts.** NORMAL → WATCH → ELEVATED → HIGH → CRITICAL, driven by deviation
from expected. Rain above its seasonal norm *suppresses*; rain below it
*escalates*. A single observation cannot reach the top tiers. Wording comes from
fixed templates — no language model anywhere in the system.

## Leakage controls

The audit that preceded this build found temporal leakage. These are the fixes,
each with a test:

| Risk | Control | Test |
|---|---|---|
| Upstream from the future | Only observations at or before *t* are matched | `test_upstream_lag_is_never_negative` |
| Scaler fitted on everything | Fitted inside the training split only | `test_scaler_not_fitted_on_full_series` |
| Rolling windows peeking | Windows cover `(t−w, t]` | `test_rolling_means_are_backward_looking` |
| Seasonal baseline from later years | Prior years only | `test_seasonal_baseline_uses_prior_years_only` |
| Rainfall climatology from later years | Prior years only | covered by the mutation test |
| Anything else | Mutate **all** future data; assert no past feature moves | `test_future_data_cannot_change_past_features` |

## Local development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q                     # test suite

python -m pipeline.rainfall.client              # rainfall (cached, incremental)
python -m pipeline.hydrology.fetch              # river geometry + place names
python -m pipeline.satellite.observations       # satellite observations
python -m pipeline.models.train                 # train both models
python -m pipeline.models.evaluate              # evaluation report
python -m pipeline.export.dashboard             # dashboard dataset

cd web && npm install && npm run dev            # dashboard at :3000
```

In production none of this is run by hand — `pipeline.yml` does it on a schedule.

## Deployment

1. Connect the repository to Vercel, root directory `web/`.
2. Enable GitHub Actions. `pipeline.yml` needs `contents: write` (already set).
3. That's all. No secrets, no environment variables, no accounts.

## Repository

| Path | Contents |
|---|---|
| `pipeline/config.py` | Monitoring network and settings |
| `pipeline/satellite/` | Scene search, band reads, quality scoring |
| `pipeline/rainfall/` | NASA POWER + Open-Meteo, caching, window features |
| `pipeline/hydrology/` | OSM river geometry, along-river distances |
| `pipeline/groundtruth/` | Schema, validation, satellite matching |
| `pipeline/features/` | The 40-feature causal builder |
| `pipeline/models/` | Splits, baseline, anomaly, versioning, training, evaluation |
| `pipeline/alerting/` | Severity, persistence, explanations |
| `pipeline/export/` | Dashboard dataset |
| `pipeline/io/` | Atomic writes, environment handling |
| `web/` | Next.js dashboard |
| `tests/` | Test suite |
| `data/` | Observations, rainfall, masks, hydrology, evaluation |
| `HICCUPS.md` | Engineering log — every failure and fix |

## Reproducibility

Dependencies are pinned exactly. Random seeds are fixed. Every model bundle
records its feature list and fingerprint, training/validation/test periods, row
counts, hyperparameters and metrics; loading a model whose fingerprint does not
match the code raises rather than silently scoring. CI enforces that on every
push.

## Licence

Code MIT. Data carries its own terms — see [`LICENSE`](LICENSE).
Contains modified Copernicus Sentinel data. River geometry © OpenStreetMap
contributors (ODbL).

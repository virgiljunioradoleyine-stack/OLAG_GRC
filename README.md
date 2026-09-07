# OLAG GRC — Pra River Pollution Early Warning

Satellite-based early warning for galamsey-driven turbidity spikes on Ghana's
Pra River. Built for GRC 2026 (Stars League — Environmental Recovery & Climate
Resilience).

**Dashboard:** https://olag-grc-viradotech.vercel.app

## The idea

Illegal gold mining fills the Pra with sediment. When a pollution slug reaches
the GWCL intake at Daboase, the plant cannot treat the water and the supply to
Sekondi-Takoradi stops — with no warning. We measure turbidity upstream from
free satellite imagery, learn what is normal for each point in each season, and
flag a rise that rainfall cannot explain, before it reaches the intake.

## How it works

1. **Imagery** — Sentinel-2 L2A, read straight from the public `sentinel-cogs`
   bucket on AWS. No account, no API key, no registration.
2. **Measurement** — NDTI = (red − green) / (red + green) over a fixed 50 m
   window at each point. Only that window is fetched, via HTTP range requests;
   a 241 MB scene is never downloaded.
3. **Finding the water** — a persistent-water mask built from the clearest
   scenes, using MNDWI rather than the Sentinel-2 water class. Sediment-laden
   water reads spectrally like bare soil, so the standard water class is blind
   to exactly the signal we measure.
4. **AI** — one Isolation Forest per monitored point (scikit-learn,
   unsupervised), trained on 7 features from the full 2017–present archive. It
   is never told what pollution looks like; it learns the normal range and
   scores how far each new reading sits outside it.
5. **Control logic** — an upstream control point suppresses false alarms. Rain
   lifts every point together, and the model has seen that combination many
   times. A rise here *without* one upstream is the rare pattern.
6. **Alert text** — deterministic templates driven by the model's own score. No
   language model, no network call: same inputs, same sentence, every time.
7. **Storage** — readings and alerts are versioned CSV/JSON committed to this
   repo. No database service.
8. **Automation** — GitHub Actions on a 3-day cron fetches new scenes, scores
   them, and commits the results back.

## Monitoring points

Verified against Sentinel-2 persistent-water masks. The coordinates in the
original brief were all off-channel and were replaced — see `HICCUPS.md`.

| Role | Point | Coordinates | Tile |
|---|---|---|---|
| control | Pra Upper Basin | 5.875062, −1.522239 | T30NXM |
| monitor | Pra at Beposo Reach | 5.423526, −1.628935 | T30NXL |
| intake | Daboase Intake (GWCL) | 5.230010, −1.569200 | T30NXL |

## Layout

| Path | What |
|---|---|
| `pipeline/points.py` | The 3 points; WGS84 → UTM → Sentinel-2 MGRS tile |
| `pipeline/search.py` | Scene discovery over the S3 bucket (replaces the STAC search API) |
| `pipeline/raster.py` | Reads every band onto one explicit grid — see the tile-edge hiccup |
| `pipeline/water.py` | MNDWI persistent-water masks |
| `pipeline/ndti.py` | Windowed COG reads and the NDTI computation |
| `pipeline/fetch.py` | STEP 1 — builds the historical record |
| `pipeline/model.py` | STEP 2 — the Isolation Forest |
| `pipeline/alerts.py` | STEP 3 — rule-based alert text |
| `pipeline/monitor.py` | STEP 4 — the scheduled run |
| `pipeline/export_web.py` | Snapshot for the dashboard |
| `web/` | STEP 5 — Next.js dashboard |
| `scripts/verify_point.py` | Is this coordinate actually on the river? |
| `scripts/tune_contamination.py` | Evidence for the contamination choice |
| `HICCUPS.md` | Engineering log — every failure and fix |

## Running it

```bash
pip install -r requirements.txt

python scripts/step0_verify.py               # stack checks
python scripts/verify_point.py <lat> <lon>   # is a coordinate on the river?
python -m pipeline.fetch                     # rebuild history (slow: ~1000 scenes/tile)
python scripts/tune_contamination.py         # compare contamination values
python -m pipeline.monitor                   # one monitoring run
python -m pipeline.export_web                # refresh the dashboard snapshot
```

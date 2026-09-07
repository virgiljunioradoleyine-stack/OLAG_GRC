# OLAG GRC — Pra River Pollution Early Warning

Satellite-based early warning for galamsey-driven turbidity spikes on Ghana's
Pra River, built for GRC 2026 (Stars League — Environmental Recovery & Climate
Resilience).

## How it works

1. **Imagery** — Sentinel-2 L2A scenes, read straight from the public
   `sentinel-cogs` bucket on AWS. No account, no API key.
2. **Measurement** — NDTI = (red − green) / (red + green), computed over a small
   window at three fixed river points. Only the window is fetched, via HTTP
   range requests; scenes are never downloaded.
3. **AI** — an Isolation Forest (scikit-learn) learns what NDTI is normal for
   each point and season, and scores each new reading for anomaly. Trained
   locally, saved as a `.pkl`, run inside GitHub Actions. No external AI API.
4. **Control logic** — an upstream control point suppresses false alarms: if
   turbidity rises everywhere at once it's rainfall, not mining.
5. **Storage** — processed readings are versioned CSV/JSON committed to this
   repo. No database service.
6. **Delivery** — GitHub Actions on a cron writes new readings; a Next.js
   dashboard on Vercel reads them.

## Layout

| Path | What |
|---|---|
| `pipeline/points.py` | The 3 monitoring points; WGS84 → UTM → Sentinel-2 MGRS tile |
| `pipeline/search.py` | Scene discovery over the S3 bucket (replaces the STAC search API) |
| `pipeline/ndti.py` | Windowed COG reads and the NDTI computation |
| `scripts/step0_verify.py` | Re-runs the STEP 0 stack checks end to end |
| `HICCUPS.md` | Engineering log — every failure and fix, for the notebook |
| `STEP0_REPORT.md` | Current status of the five STEP 0 checks |
| `web/` | Next.js dashboard |

## Running the checks

```bash
pip install -r requirements.txt
python scripts/step0_verify.py
```

## Status

STEP 0 in progress — see `STEP0_REPORT.md`. Two blockers are open and need a
team decision before STEP 1 (historical data collection) can start.

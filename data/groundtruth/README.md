# Ground truth — how to add real measurements

**This directory contains no measurement data, and that is deliberate.**

We searched for an anonymous, programmatic source of Ghanaian in-situ
water-quality data and did not find one. Evidence is recorded in
`data/sources/probe_evidence.json` (probed from GitHub Actions, 2026-09-07):

| Source | Result |
|---|---|
| `data.gov.gh` CKAN API | Connection refused — portal appears offline |
| GEMStat (UNEP) | Portal loads; data needs a manual request form, no anonymous API |
| Water Quality Portal (US EPA/USGS) | Works, but United States only — used here only as a **schema** reference |
| Ghana Water Company, Water Research Institute, EPA Ghana | No open data API found |

Because there is no ground truth, the system reports a **satellite-derived
anomaly indicator**, not turbidity in NTU. Nothing in this project converts a
satellite index into an NTU figure, and nothing should until real measurements
exist to calibrate against.

## Adding data

Drop a CSV in this directory matching `TEMPLATE.csv`. The supervised calibration
model (Model C) trains automatically once enough valid rows exist.

| Column | Required | Notes |
|---|---|---|
| `sample_date` | ✅ | `YYYY-MM-DD` |
| `station_id` | ✅ | must match a station in `pipeline/config.py` (P01–P08) |
| `characteristic` | ✅ | `turbidity`, `tss`, `conductivity`, `ph` |
| `value` | ✅ | numeric |
| `unit` | ✅ | `NTU`, `FNU`, `mg/L`, `uS/cm`, `pH` |
| `organisation` | ✅ | who measured it |
| `source_url` | ✅ | where it came from |
| `latitude`, `longitude`, `depth_m`, `method`, `notes` | optional | |

Validation runs in CI (`tests/test_groundtruth.py`) and will reject unknown
station IDs, unrecognised units, negative values and missing provenance.

## Rules

1. **Never fabricate rows here.** A fabricated measurement would silently
   invalidate every result downstream and is worse than having no data.
2. Provenance is mandatory — `organisation` and `source_url` are required so any
   number can be traced back.
3. Samples are matched to satellite observations within **1 day** by default.
   Turbidity changes within hours; a looser window pairs measurements that
   describe different river states.

## Realistic ways to obtain data

- Ghana Water Company Ltd operational logs for the Daboase headworks — the
  plant records raw-water turbidity continuously for treatment purposes.
- CSIR Water Research Institute sampling campaigns.
- Published papers on Pra basin water quality often tabulate dated NTU/TSS
  values; these can be transcribed with the citation in `source_url`.

Even 20–50 dated measurements at a known station would move this project from
"unusual satellite reading" to a calibrated, validated turbidity estimate.

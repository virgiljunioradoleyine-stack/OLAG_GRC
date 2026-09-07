# Historical documents

These describe an **earlier version** of this project — a three-station system
using a 7-feature Isolation Forest, before the platform rebuild. They are kept
because the engineering notebook needs the record, not because they are current.

| File | What it was | Superseded by |
|---|---|---|
| `STEP0_REPORT.md` | Stack verification for the original 3-point build | `README.md` and `data/sources/probe_evidence.json` |
| `TEST_RESULTS_v1.md` | Test results for the 3-station, NDTI-only, no-rainfall system | `data/evaluation/evaluation.json` and `EVALUATION.md` |
| `control_*.png` | Analysis figures for the old control point (now P01) | — |

**Do not cite the numbers in these files as current.** The current system has
eight stations, 40 causal features, rainfall data, an expected-condition
baseline, chronological validation and empirically calibrated alert thresholds.
Everything in `TEST_RESULTS_v1.md` predates all of that.

The one finding worth carrying forward: against the single documented pollution
incident we could date (Daboase, 14 August 2026, 11,955 NTU against a 500 NTU
limit), the old system scored the nearest readings as entirely normal. That
failure is what motivated adding absolute reflectance, rainfall, a larger
sampling reach and an expected-condition model.

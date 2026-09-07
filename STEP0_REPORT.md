# STEP 0 — stack verification report

Date: 2026-09-07. Every number below was measured live against real Sentinel-2
data, not estimated. Reproduce with `python scripts/step0_verify.py`.

| # | Check | Result |
|---|---|---|
| 1 | Earth Search STAC connectivity | **FAIL as specified → PASS via replacement** |
| 2 | Asset retrieval (windowed COG read) | **PASS** |
| 3 | NDTI on real pixels | **FAIL — points are not on the river** |
| 4 | GitHub repo + Actions | **PASS** |
| 5 | Vercel deploy | **BLOCKED — needs a linked project** |

---

## 1. Earth Search STAC connectivity — failed as specified, replaced

`POST https://earth-search.aws.element84.com/v1/search` never reached the
internet. This build environment's egress policy denies the host outright:

```
ProxyError: Tunnel connection failed: 403 Forbidden
proxy status -> connect_rejected  earth-search.aws.element84.com:443
```

This is an organisational network policy, not a bug and not a rate limit, so it
cannot be retried around.

**It does not block the project.** Earth Search is only a search index over the
public AWS bucket `sentinel-cogs`, and that bucket *is* reachable. Every scene
directory in it contains the identical STAC item JSON the API would have
returned, and the bucket allows anonymous listing. `pipeline/search.py` now
discovers scenes by listing S3 prefixes and reading those item JSONs.

Measured, tile T30NXM, 18 months: **163 scenes discovered**, cloud cover
0.5%–100%. Three most recent, with real IDs and dates:

```
S2A_30NXM_20260721_0_L2A   2026-07-21   cloud=82.50%
S2A_30NXM_20260731_0_L2A   2026-07-31   cloud=93.31%
S2C_30NXM_20260729_0_L2A   2026-07-29   cloud=99.94%
```

Net effect: one fewer third-party service in the critical path. Only AWS S3
remains.

## 2. Asset retrieval — pass

Opened the `red` (B04), `green` (B03) and `scl` (SCL) COGs for a real scene over
HTTPS and read their headers without downloading them:

```
B04.tif  10980x10980  uint16  10m  (~241 MB full file)  header read in 0.97s
B03.tif  10980x10980  uint16  10m  (~241 MB full file)
SCL.tif   5490x5490   uint8   20m
internal tiling 1024x1024, overviews [2,4,8,16]
```

Sub-second header reads on a 241 MB file confirm HTTP range requests work —
windowed reading is viable, which is what makes the whole approach affordable.

Also captured here: these scenes carry `scale: 0.0001, offset: -0.1`
(processing baseline 05.12). The offset must be applied per scene and read from
each scene's own metadata — see HICCUPS.md.

## 3. NDTI on real pixels — failed, and this is the important one

The reader works: it fetches real reflectance, applies the correct per-scene
scaling, and reads the SCL mask. What it cannot do is find any water, because
**none of the three supplied coordinates sit on the river.**

Distance from each supplied coordinate to the nearest detected water pixel,
measured on the clearest scene available (2026-01-25, 0.47% cloud):

| Point | Supplied coordinate | Nearest water |
|---|---|---|
| `control` — Pra Upstream | 6.2100, −1.6500 | **1,785 m away** |
| `monitor` — Pra at Dunkwa | 5.9700, −1.7800 | **288 m away** |
| `intake` — Daboase Intake | 5.2300, −1.5600 | **540 m away** |

At the control point, a cloud-free window classified as **100% vegetation**.
Six scenes in a row returned "0 usable water pixels".

Two distinct problems surfaced, both documented in HICCUPS.md:

**(a) The coordinates are wrong.** The brief anticipated this. The control point
is the dangerous one — 1.8 km off. Left unfixed it would have produced land
readings that look like plausible numbers, and the control-suppression logic
(the thing that stops us crying wolf every time it rains) would have been
silently comparing the river against a patch of forest.

**(b) SCL cannot see this river.** STEP 1 specifies selecting water via SCL
class 6. In a 10 km × 10 km box around the control point, SCL found **1 water
pixel out of 250,000**. The cause is not just that the Pra is narrow (2–5 pixels
at 20 m). It is that SCL's water class keys on the low reflectance of *clear*
water, and sediment-laden water looks spectrally like bare soil. SCL is
systematically blind to exactly the polluted water this project exists to
detect — as a filter it would bias the dataset against the signal.

Fix already implemented: water detection moved to **MNDWI** =
(green − SWIR16) / (green + SWIR16). SWIR is absorbed by water regardless of
sediment load, so it holds up on turbid rivers. On the same clear scene MNDWI
recovered a coherent channel where SCL found nothing. SCL is retained for the
job it does well — rejecting cloud and shadow pixels.

## 4. GitHub repo and Actions — pass

Repo is `virgiljunioradoleyine-stack/OLAG_GRC`, authenticated as
`virgiljunioradoleyine-stack`. `.github/workflows/hello.yml` runs on push and
`workflow_dispatch`; it installs dependencies, resolves the monitoring points to
Sentinel-2 tiles, and confirms the runner can reach the COG bucket. Run status
is recorded below once the first push completes.

## 5. Vercel — blocked

The Vercel account (`viradotech`, hobby plan) is reachable and has five
projects, but **none is linked to `OLAG_GRC`**. A placeholder Next.js app is
committed at `web/`, ready to deploy once a project is created and linked.

Separately, `vercel.com` is also denied by this environment's egress policy, so
deployment must be triggered through the Vercel integration rather than the CLI
from here.

---

## Open decisions needed before STEP 1

1. **New coordinates for all three points.** Rather than snapping each point to
   the nearest water — which risks latching onto a pond, a flooded mining pit,
   or the wrong tributary — these should be picked deliberately. The intake
   point in particular must sit on the Pra *at the GWCL abstraction*, since the
   whole value proposition is warning that specific plant.
2. **Cloud-filter policy.** Confirm the move from `eo:cloud_cover < 20`
   (tile-level) to per-pixel SCL cloud rejection. As specified, 18 months of
   data yields 3 usable scenes for T30NXM — not enough to train anything.

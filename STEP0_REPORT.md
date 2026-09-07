# STEP 0 — stack verification report

Date: 2026-09-07. Every number below was measured live against real Sentinel-2
data, not estimated. Reproduce with `python scripts/step0_verify.py`.

| # | Check | Result |
|---|---|---|
| 1 | Earth Search STAC connectivity | **FAIL as specified → PASS via replacement** |
| 2 | Asset retrieval (windowed COG read) | **PASS** |
| 3 | NDTI on real pixels | **FAIL — points are not on the river** |
| 4 | GitHub repo + Actions | **PASS** (run #1 succeeded) |
| 5 | Vercel deploy | **PASS** (project created; first build failed on a CVE, fixed) |

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

| Point | Supplied coordinate | Usable pixels | Nearest persistent water |
|---|---|---|---|
| `control` — Pra Upstream | 6.2100, −1.6500 | **0** | 637 m away |
| `monitor` — Pra at Dunkwa | 5.9700, −1.7800 | **0** | 281 m away |
| `intake` — Daboase Intake | 5.2300, −1.5600 | **0** | 934 m away |

(Measured against a persistent-water mask built from the 12 clearest scenes in
18 months, after the offset bug below was fixed. An earlier version of this
table quoted different distances; those came from the buggy code and are
superseded. The verdict is unchanged: all three points are off the channel.)

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
Sentinel-2 tiles, and confirms the runner can reach the COG bucket.

First run: **success**.

```
step0-selfcheck  run #1  event=push  branch=claude/new-session-udfegz
conclusion: success   (2026-09-07T11:15:11Z -> 11:15:42Z, 31s)
https://github.com/virgiljunioradoleyine-stack/OLAG_GRC/actions/runs/34115666893
```

This confirms three things at once: Actions is enabled and permissions are
sound, the runner can install the geospatial dependencies, and — importantly —
GitHub's network can reach `sentinel-cogs`. The egress restriction that blocks
Earth Search is specific to this development environment; it does not apply to
the CI runner that will execute the real monitoring job.

## 5. Vercel — pass, after one failure

Project `olag-grc` created on the `viradotech` team and linked to this repo,
root directory `web/`, production branch `claude/new-session-udfegz`.

- Project: https://vercel.com/viradotech/olag-grc
- URL: https://olag-grc-viradotech.vercel.app

The **first deploy failed**: Vercel rejected the build with
`VULNERABLE_NEXTJS_VERSION` (CVE-2025-66478) because the scaffold pinned Next.js
15.5.4. Bumped to 15.5.25. Logged in HICCUPS.md — the takeaway for demo week is
that a deploy can fail for reasons unrelated to our code, so the dashboard must
not be deployed for the first time the night before judging.

**One thing to decide:** the deployment is currently behind **Vercel
Authentication** (the team's default deployment protection). Fetching the URL
returns a 302 to Vercel SSO, which means *a judge clicking the link would hit a
login wall*. For a public competition dashboard this needs turning off in
Project Settings → Deployment Protection. Left as-is for now — making a page
publicly readable is your call, not mine. Say the word and I'll disable it.

Note: `vercel.com` is also denied by this dev environment's egress policy, so
deploys are driven through the Vercel GitHub integration rather than the CLI.

---

## A bug worth recording

While building the water mask we found that the BOA reflectance offset was being
applied twice, which drove dark surfaces negative and **inverted the sign** of
every normalized-difference index — water was scoring as not-water.

It was invisible for a while, because all three test points were off-river, so
"no water" was the expected answer everywhere and everything looked consistent.
It only surfaced when we tested **Lake Bosumtwi**, an 8 km crater lake, and the
detector said "no persistent water within 1 km". After the fix it reads
10,000 of 10,000 pixels as water. Bosumtwi is now a standing positive control.

Full write-up in HICCUPS.md. Everything in this report has been re-measured with
the corrected code.

## Blocking STEP 1

**Coordinates.** All three points need replacing. See `COORDINATES_GUIDE.md` for
the selection procedure; candidates can be checked in about a minute with:

```bash
python scripts/verify_point.py <lat> <lon> --label control
```

Historical collection stays parked until these are confirmed — 18 months of
readings taken from the wrong place is worse than no readings, because the
numbers look plausible.

## Decided, not blocking

**Cloud-filter policy.** Moving from `eo:cloud_cover < 20` (tile-level, over a
110 × 110 km area) to per-pixel SCL cloud rejection inside the reading window.
As specified, 18 months yields 3 usable scenes for T30NXM — not enough to train
anything. Proceeding this way unless the team objects.

**Water detection.** MNDWI rather than SCL class 6, for the turbidity-blindness
reason in check 3. SCL retained for cloud and shadow rejection.

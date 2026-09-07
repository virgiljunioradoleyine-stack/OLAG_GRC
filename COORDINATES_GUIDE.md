# How to pick the three monitoring coordinates

The three coordinates in the brief don't sit on water. This is how to replace
them, using free sites with no account required, and how to prove each one is
right before we build 18 months of data on top of it.

**You pick, I verify.** Send me a lat/lon and I'll check it against real
Sentinel-2 pixels in about a minute, or run it yourself:

```bash
python scripts/verify_point.py 6.21093 -1.65568 --label control
```

You'll get one of three verdicts:

```
VERDICT: GOOD           -- on the river, N pixels per reading
VERDICT: MARGINAL       -- only 3-7 pixels, readings will be noisy
VERDICT: OFF THE CHANNEL -- with the nearest real water suggested
```

This checks the actual satellite data we'll be reading, not a map tile. A spot
can look like a river on Google Maps and still fail, because Google's imagery
may be from a different year or a different season.

---

## What each point has to be

| Point | Where it must sit | Why it matters |
|---|---|---|
| `intake` | On the Pra **at the GWCL Daboase abstraction** | This is the whole product. The warning is "Daboase is about to receive dirty water", so we must measure the water that plant actually draws. |
| `monitor` | On the river **upstream of the intake**, in a mining-affected reach | This is where a pollution event gets detected early enough to be useful. Needs enough travel time downstream to Daboase to be a warning rather than a news report. |
| `control` | On the river system **upstream of the mining**, same rainfall | This is what stops false alarms. When it rains, turbidity rises everywhere; if the control rises too, we suppress the alert. If the control is somewhere that also gets mined, it rises during real events too and we suppress alerts we should be sending. |

**The control point is the one to get right.** It's doing the hardest job and
it's the easiest to get subtly wrong.

### One thing to decide about `monitor`

The brief calls it "Pra at Dunkwa", and the supplied coordinate (5.9700,
−1.7800) is Dunkwa town. But Dunkwa-on-Offin sits on the **Offin River**, a
major tributary of the Pra, not the Pra mainstem. Worth confirming on OSM.

That's not necessarily wrong — the Offin is heavily mined and joins the Pra
upstream of Daboase, so an Offin point is hydrologically valid as an early
warning for Daboase. But we should name it honestly ("Offin at Dunkwa"), and a
judge may well ask. Your call:

- **Keep Dunkwa on the Offin** — strong galamsey signal, real early warning.
- **Move to the Pra mainstem** — matches the name, may be a weaker signal.

---

## Step 1 — Confirm which river you're looking at (OpenStreetMap)

Do this first. It's the step that stops you putting the "Pra" point on a
tributary, which is exactly what may have happened at Dunkwa.

1. Go to **[openstreetmap.org](https://www.openstreetmap.org)**
2. Search `Daboase, Ghana` (then `Dunkwa-on-Offin, Ghana`)
3. Zoom until you see the blue river line
4. **Click directly on the river line.** The left panel names it — "Pra River",
   "Offin River", etc. This is the authoritative check.

No account needed.

## Step 2 — Find the exact channel (Google Maps satellite)

OSM gives you the river's identity; satellite view gives you its exact position.

1. Go to **[google.com/maps](https://www.google.com/maps)**
2. Search the same place, switch to **Satellite** (bottom-left thumbnail)
3. Zoom right in until the river is a wide visible band, not a thin line
4. **Right-click the middle of the channel** — the top of the menu shows
   `5.223, -1.564`. **Click it to copy.**

Aim for these when choosing the exact spot:

- **The middle of the channel**, not the bank. Bank pixels mix water and land
  and give us false turbidity readings.
- **The widest stretch** you can find near the right location. Sentinel-2 is
  10 m per pixel, so a 40 m channel is 4 pixels and a 100 m channel is 10. More
  pixels means a more reliable reading. It's worth moving a few hundred metres
  upstream or downstream to find a wide, straight reach.
- **Avoid**: bridges, confluences where two rivers meet, sandbars, and the edges
  of ponds or flooded mining pits next to the river.

## Step 3 — Cross-check the location is real (optional but useful)

Google's satellite imagery can be several years old, and rivers move.

- **[Esri World Imagery Wayback](https://livingatlas.arcgis.com/wayback/)** —
  no account, lets you step through imagery from different years. If the channel
  sits in the same place across several years, it's stable.
- **[Google Earth Web](https://earth.google.com/web)** — no account, has a
  historical imagery slider.
- **[Sentinel Hub EO Browser](https://apps.sentinel-hub.com/eo-browser/)** —
  this shows the *exact* Sentinel-2 imagery we use, so it's the closest match to
  what the pipeline sees. It does need a free account, so it's optional; my
  verifier script gives you the same answer without signing up.

## Step 4 — Send me the coordinates

Paste them in any format:

```
control  6.xxxxx, -1.xxxxx
monitor  5.xxxxx, -1.xxxxx
intake   5.xxxxx, -1.xxxxx
```

I'll run each through the verifier and report pixel counts and verdicts. If one
comes back MARGINAL or OFF THE CHANNEL, I'll tell you which way to nudge it.

Getting one wrong isn't expensive — the check takes a minute. Getting one wrong
*and not noticing* is expensive, because we'd train the model on 18 months of
readings taken from a patch of forest.

---

## Where to start looking

Starting points only — verify each one, don't trust this table.

| Point | Search on OSM | Then look for |
|---|---|---|
| `intake` | `Daboase, Ghana` | The Pra beside the GWCL waterworks. If you can find the intake structure itself in satellite view, put the point in the channel just upstream of it. |
| `monitor` | `Dunkwa-on-Offin, Ghana` | The Offin where it passes the town — click the line to confirm the name. Pick a wide reach away from the bridge. |
| `control` | `Twifo Praso` or `Assin Praso, Ghana` | The Pra mainstem well upstream. **Check upstream of your choice for mining scars** — bare orange-brown patches and pitted ground beside the river. If they're there, keep moving upstream. |

The mining scars are visible from satellite view once you know the look: raw
earth, no vegetation, irregular water-filled pits right against the riverbank.
For the control point you want a reach with none of that upstream of it.

If you can't find a clean control on the Pra mainstem, tell me — we can look at
a less-mined tributary instead. That's a design change worth making early
rather than discovering the control doesn't work during testing.

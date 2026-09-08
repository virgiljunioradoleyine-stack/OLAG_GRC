import fs from "node:fs";
import path from "node:path";

/**
 * Add a monitoring station from the Live Map, in one click.
 *
 * The click used to open a prefilled GitHub issue and leave the user to press
 * Submit. This route does that step server-side instead, so the button just
 * works — but it still creates the issue rather than committing directly,
 * because the issue is the audit trail: it records who asked, what was
 * validated, what the pipeline found, and it is where the workflow reports
 * back. Nothing about the existing add-station workflow changes.
 *
 * WHY THERE IS A KEY. A public site with a write path and no login is a write
 * path for everyone who finds it. The project forbids third-party auth
 * (Auth0, Clerk and the like), so this uses the smallest thing that actually
 * works: a shared key held in an environment variable, entered once by the
 * operator. It is not a user-accounts system and does not pretend to be. The
 * candidate-matching below is the real containment — even with the key, a
 * request can only name a point the pipeline itself has already measured.
 *
 * If the environment variables are absent the route reports that plainly and
 * the UI falls back to the GitHub issue link, which needs no secret at all.
 * The feature degrades; it does not break.
 */

export const dynamic = "force-dynamic";

const REPO = process.env.STATION_REPO || "virgiljunioradoleyine-stack/OLAG_GRC";
const TOLERANCE_M = 60;      // a click snaps to a candidate before it is sent
const MIN_SEPARATION_M = 400; // do not sit on top of an existing station

function readData(name, fallback) {
  try {
    return JSON.parse(
      fs.readFileSync(path.join(process.cwd(), "public", "data", name), "utf8"));
  } catch {
    return fallback;
  }
}

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371008.8, r = (d) => (d * Math.PI) / 180;
  const p1 = r(lat1), p2 = r(lat2);
  const dp = p2 - p1, dl = r(lon2 - lon1);
  const h = Math.sin(dp / 2) ** 2
    + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

const bad = (status, error, extra = {}) =>
  Response.json({ ok: false, error, ...extra }, { status });

export async function POST(request) {
  const token = process.env.STATION_BOT_TOKEN;
  const key = process.env.ADD_STATION_KEY;
  if (!token || !key) {
    // Not an error the user can fix by retrying — tell the UI to use the
    // no-secret path instead of failing in their face.
    return bad(503, "One-click adding is not configured on this deployment.",
               { fallback: "issue" });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return bad(400, "Could not read the request.");
  }

  if (typeof body.key !== "string" || body.key.length !== key.length
      || !timingSafeEqual(body.key, key)) {
    return bad(401, "That key is not right.", { needsKey: true });
  }

  const lat = Number(body.lat), lon = Number(body.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return bad(400, "No coordinates in the request.");
  }

  // ---- the real containment: it must be a point we already measured -------
  const candidates = readData("candidates.geojson", { features: [] }).features || [];
  if (!candidates.length) {
    return bad(409, "No candidate sites are published yet, so no point can be "
                  + "verified. Wait for a pipeline run to finish.");
  }
  let best = null, bestD = Infinity;
  for (const f of candidates) {
    const [clon, clat] = f.geometry.coordinates;
    const d = haversineM(lat, lon, clat, clon);
    if (d < bestD) { best = f; bestD = d; }
  }
  if (bestD > TOLERANCE_M) {
    return bad(422, `That point is not a verified candidate site — the nearest `
                  + `is ${Math.round(bestD).toLocaleString()} m away. Only sites `
                  + `the pipeline has checked against the satellite water mask `
                  + `can be added.`);
  }

  const stations = readData("stations.json", []);
  for (const s of stations) {
    const d = haversineM(best.geometry.coordinates[1],
                         best.geometry.coordinates[0], s.lat, s.lon);
    if (d < MIN_SEPARATION_M) {
      return bad(409, `That site is only ${Math.round(d).toLocaleString()} m from `
                    + `${s.id} (${s.name}). Stations that close measure the same `
                    + `water, so it would add readings without adding information.`);
    }
  }

  const [clon, clat] = best.geometry.coordinates;
  const props = best.properties || {};
  const nums = stations.map((s) => parseInt(String(s.id).replace(/\D/g, ""), 10))
    .filter(Number.isFinite);
  const nextId = "P" + String((nums.length ? Math.max(...nums) : 0) + 1)
    .padStart(2, "0");
  const name = String(body.name || "").trim().slice(0, 60) || `Pra Reach ${nextId}`;

  const req = { lat: Number(clat.toFixed(6)), lon: Number(clon.toFixed(6)),
                name, role: "monitor" };
  const issueBody = [
    "Added from the Live Map.",
    "",
    `- **${name}** at \`${req.lat}, ${req.lon}\``,
    `- ${props.water_pixels} usable water pixels, tile \`${props.tile}\``,
    `- snapped ${Math.round(bestD)} m from the click`,
    "",
    "```json",
    JSON.stringify(req, null, 2),
    "```",
    "",
    "The add-station workflow will validate this, collect the station's full",
    "Sentinel-2 history, rebuild the dashboard and report back here.",
  ].join("\n");

  let res;
  try {
    res = await fetch(`https://api.github.com/repos/${REPO}/issues`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title: `[station] ${name}`, body: issueBody }),
    });
  } catch {
    return bad(502, "Could not reach GitHub.", { fallback: "issue" });
  }
  if (!res.ok) {
    // Never surface GitHub's response verbatim: it can echo token scope detail.
    return bad(502, `GitHub refused the request (${res.status}).`,
               { fallback: "issue" });
  }
  const issue = await res.json();

  return Response.json({
    ok: true,
    id: nextId,
    name,
    lat: req.lat,
    lon: req.lon,
    water_pixels: props.water_pixels ?? null,
    tile: props.tile ?? null,
    snapped_m: Math.round(bestD),
    tracking_url: issue.html_url,
  });
}

/** Constant-time compare, so the key cannot be recovered by timing. */
function timingSafeEqual(a, b) {
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

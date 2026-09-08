/**
 * Browser smoke test for the dashboard.
 *
 * This exists because of a bug nothing else could catch. The Leaflet map was
 * built with `L.map(...)` and had its layers added before any view was set.
 * Leaflet cannot project a coordinate without a view, so the first vector
 * layer threw and took the rest of the setup with it -- while tile layers,
 * which defer until the map reports loaded, carried on. The result was a map
 * showing satellite imagery with no stations and no river on it.
 *
 * Every Python test passed. The production build passed. Every page returned
 * 200. The only way to see it was to run the page in a browser and count the
 * things that were supposed to be drawn.
 */
import { chromium } from "playwright";

const BASE = process.env.SMOKE_BASE || "http://localhost:3000";
const PAGES = ["/", "/map", "/trends", "/alerts", "/reports", "/about"];

// Stations plus river segments. Anything above zero proves the renderer ran;
// requiring the station count proves every station was actually drawn.
const MAP_PAGES = new Set(["/", "/map"]);

let failures = 0;
const fail = (m) => { console.error("FAIL " + m); failures++; };

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
try {
  for (const path of PAGES) {
    const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    // Third-party tiles and fonts are not the subject of this test, and CI
    // should not fail because Esri is slow. Block everything off-origin.
    await page.route("**", (r) =>
      r.request().url().startsWith(BASE) ? r.continue() : r.abort());

    const res = await page.goto(BASE + path, { waitUntil: "load", timeout: 30000 });
    if (!res || res.status() !== 200) fail(`${path} returned ${res && res.status()}`);
    await page.waitForTimeout(3500);

    const seen = await page.evaluate(() => ({
      h1: document.querySelector("h1")?.textContent || null,
      vectors: document.querySelectorAll("path.leaflet-interactive").length,
      mapContainers: document.querySelectorAll(".leaflet-container").length,
      stationsInLabel: Number(
        (document.querySelector("[aria-label^='Map of ']")?.getAttribute("aria-label")
          || "").match(/Map of (\d+)/)?.[1] || 0),
    }));

    if (errors.length) fail(`${path} raised: ${errors[0].slice(0, 200)}`);
    if (!seen.h1) fail(`${path} rendered no heading`);

    if (MAP_PAGES.has(path)) {
      if (!seen.mapContainers) fail(`${path} rendered no map`);
      else if (seen.vectors < seen.stationsInLabel) {
        fail(`${path} drew ${seen.vectors} vectors for ${seen.stationsInLabel} `
             + `stations — the map is missing its points`);
      }
    }
    console.log(`ok ${path} — ${seen.h1} (${seen.vectors} vectors, `
                + `${seen.stationsInLabel} stations)`);
    await ctx.close();
  }
} finally {
  await browser.close();
}

// ---- the add-station route -------------------------------------------
// CI has no key and no token, so what is checkable here is the contract the
// UI depends on: an unconfigured deployment must say so and ask for the
// GitHub fallback rather than failing, and an unverified point must be
// refused. The refusal is the security boundary, so it is worth a test that
// runs without any secret at all.
{
  const post = async (body) => {
    const r = await fetch(BASE + "/api/stations", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };

  const unconfigured = await post({ lat: 5.85, lon: -1.54 });
  if (process.env.ADD_STATION_KEY) {
    console.log("ok /api/stations — skipped contract check (key is configured)");
  } else if (unconfigured.status !== 503 || unconfigured.json.fallback !== "issue") {
    fail(`/api/stations unconfigured returned ${unconfigured.status} `
         + `${JSON.stringify(unconfigured.json)} — the UI needs 503 + `
         + `fallback:"issue" to offer the GitHub path`);
  } else {
    console.log("ok /api/stations — unconfigured deployment asks for the fallback");
  }

  const noBody = await post({});
  if (noBody.status < 400) {
    fail("/api/stations accepted a request with no coordinates");
  } else {
    console.log("ok /api/stations — rejects a request with no coordinates");
  }
}

if (failures) {
  console.error(`\n${failures} smoke failure(s)`);
  process.exit(1);
}
console.log("\nsmoke: all pages render");

import fs from "node:fs";
import path from "node:path";

const DIR = path.join(process.cwd(), "public", "data");

/** Read one exported JSON file. Returns `fallback` when the pipeline has not
 *  produced it yet, so the UI can show an honest empty state instead of
 *  crashing or inventing numbers. */
function read(name, fallback) {
  try {
    return JSON.parse(fs.readFileSync(path.join(DIR, name), "utf8"));
  } catch {
    return fallback;
  }
}

export const getSummary = () => read("summary.json", null);
export const getStations = () => read("stations.json", []);
export const getSeries = () => read("series.json", {});
export const getAlerts = () => read("alerts.json", { alerts: [], detailed: [] });
export const getRiver = () => read("river.geojson", null);
export const getNetwork = () => read("network.json", {});

export function getAll() {
  return {
    summary: getSummary(),
    stations: getStations(),
    series: getSeries(),
    alerts: getAlerts(),
    river: getRiver(),
    network: getNetwork(),
  };
}

/** Severity ordering, used for sorting and for picking the worst status. */
export const SEVERITY_ORDER = ["NO_DATA", "NORMAL", "WATCH", "ELEVATED", "HIGH", "CRITICAL"];

export function worstSeverity(list) {
  return list.reduce(
    (acc, s) =>
      SEVERITY_ORDER.indexOf(s) > SEVERITY_ORDER.indexOf(acc) ? s : acc,
    "NORMAL"
  );
}

export function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function daysSince(iso) {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

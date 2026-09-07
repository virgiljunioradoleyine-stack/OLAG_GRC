import fs from "node:fs";
import path from "node:path";
import Dashboard from "./Dashboard";

// Read at build time. The pipeline writes this snapshot into public/data so the
// dashboard has no dependency on the pipeline's layout outside web/.
function loadData() {
  const p = path.join(process.cwd(), "public", "data", "dashboard.json");
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return { points: [], alerts: [], features: [], generated_at: null };
  }
}

export default function Home() {
  return <Dashboard data={loadData()} />;
}

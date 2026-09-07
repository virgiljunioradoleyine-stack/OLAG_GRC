"use client";
import { useMemo, useState } from "react";
import { Empty, Panel, Severity } from "./Ui";

const PERIODS = [
  { key: "30", label: "Last 30 days", days: 30 },
  { key: "90", label: "Last 90 days", days: 90 },
  { key: "365", label: "Last 12 months", days: 365 },
  { key: "all", label: "Full record", days: null },
];

function since(days) {
  if (!days) return "1970-01-01";
  return new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
}

export default function Reports({ summary, stations, series, alerts }) {
  const [period, setPeriod] = useState("90");
  const days = PERIODS.find((p) => p.key === period)?.days;
  const from = since(days);
  const to = new Date().toISOString().slice(0, 10);

  const report = useMemo(() => {
    const inRange = (rows) => (rows || []).filter((r) => r.date >= from);
    const perStation = stations.map((s) => {
      const rows = inRange(series?.[s.id]);
      const vals = rows.map((r) => r.indicator).filter((v) => v != null);
      const quality = rows.reduce((acc, r) => {
        acc[r.quality] = (acc[r.quality] || 0) + 1; return acc;
      }, {});
      return {
        ...s,
        n: rows.length,
        mean: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null,
        max: vals.length ? Math.max(...vals) : null,
        quality,
        anomalies: rows.filter((r) => r.anomaly).length,
      };
    });
    const alertsInRange = (alerts?.alerts || []).filter((a) => a.date >= from);
    const rains = stations
      .map((s) => s.latest?.rain_7d).filter((v) => v != null);
    return { perStation, alertsInRange, rains };
  }, [stations, series, alerts, from]);

  const bySeverity = report.alertsInRange.reduce((acc, a) => {
    acc[a.severity] = (acc[a.severity] || 0) + 1; return acc;
  }, {});

  const models = stations.filter((s) => s.model).map((s) => s.model);
  const modelVersions = [...new Set(models.map((m) => m.model_version))];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Reports</h1>
          <p className="subtitle">
            Monitoring summary for the selected period, generated from the pipeline
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <label htmlFor="period" className="sr-only">Reporting period</label>
          <select id="period" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
          <button className="btn" onClick={() => window.print()}>
            Download / print
          </button>
        </div>
      </div>

      <Panel title="Reporting period"
             sub={`${from} to ${to} · generated ${summary?.generated_at?.slice(0, 10) || "—"}`}>
        <dl className="kv">
          <dt>Indicator</dt>
          <dd>{summary?.indicator?.name} ({summary?.indicator?.short})</dd>
          <dt>Monitoring locations</dt>
          <dd>{stations.length} ({summary?.stations_with_data} with observations)</dd>
          <dt>Observations in period</dt>
          <dd>{report.perStation.reduce((a, s) => a + s.n, 0)}</dd>
          <dt>Alerts in period</dt>
          <dd>
            {report.alertsInRange.length}
            {Object.keys(bySeverity).length > 0 && (
              <> — {Object.entries(bySeverity).map(([k, v]) => `${v} ${k}`).join(", ")}</>
            )}
          </dd>
          <dt>Model version(s)</dt>
          <dd>{modelVersions.join(", ") || "no model trained"}</dd>
          <dt>Ground truth</dt>
          <dd>
            {summary?.ground_truth_records
              ? `${summary.ground_truth_records} in-situ records`
              : "none — the indicator is uncalibrated and is not reported in NTU"}
          </dd>
        </dl>
      </Panel>

      <div style={{ marginTop: 16 }}>
        <Panel title="Per-station summary" bodyStyle={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table>
              <caption className="sr-only">Station summary for the reporting period</caption>
              <thead>
                <tr>
                  <th scope="col">Station</th>
                  <th scope="col" className="num">Obs</th>
                  <th scope="col" className="num">Mean</th>
                  <th scope="col" className="num">Max</th>
                  <th scope="col" className="num">Flagged</th>
                  <th scope="col">Quality (GOOD/ACC/LOW)</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {report.perStation.map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}<div style={{ color: "var(--faint)", fontSize: 11.5 }}>{s.id} · {s.role}</div></td>
                    <td className="num">{s.n}</td>
                    <td className="num">{s.mean != null ? s.mean.toFixed(3) : "—"}</td>
                    <td className="num">{s.max != null ? s.max.toFixed(3) : "—"}</td>
                    <td className="num">{s.anomalies}</td>
                    <td className="num">
                      {s.quality.GOOD || 0} / {s.quality.ACCEPTABLE || 0} / {s.quality.LOW_QUALITY || 0}
                    </td>
                    <td><Severity value={s.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {models[0] && (
        <div style={{ marginTop: 16 }}>
          <Panel title="Model information" sub="Applies to every station model in this build">
            <dl className="kv">
              <dt>Algorithm</dt><dd>{models[0].algorithm}</dd>
              <dt>Feature version</dt><dd>{models[0].feature_version} ({models[0].n_features} features)</dd>
              <dt>Training period</dt><dd>{models[0].training_start} → {models[0].training_end}</dd>
              <dt>Validation period</dt><dd>{models[0].validation_start || "—"} → {models[0].validation_end || "—"}</dd>
              <dt>Test period</dt><dd>{models[0].test_start || "—"} → {models[0].test_end || "—"}</dd>
              <dt>Trained at</dt><dd>{models[0].created_at}</dd>
            </dl>
          </Panel>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <Panel title="Methodology and limitations">
          <div className="prose">
            <p>
              Observations are derived from Sentinel-2 L2A imagery over a fixed
              reach at each station. Water pixels come from a persistent-water
              mask; cloud and shadow are rejected per pixel using the scene
              classification layer. Rainfall is taken from NASA POWER, with
              Open-Meteo ERA5 as a fallback.
            </p>
            <p>
              An expected-condition model predicts what the index should be given
              season, recent rainfall and upstream state. The deviation from that
              expectation, corroborated by an unsupervised anomaly detector and
              gated on persistence and data quality, determines severity.
            </p>
            <p>
              <strong>Limitations.</strong> There are no in-situ water-quality
              measurements available for this basin, so the index is not
              calibrated to NTU or TSS and is not reported as such. Satellite
              revisit and cloud cover mean observations are irregular and can lag
              an event by several days. The system identifies unusual conditions
              for investigation; it does not prove the presence of illegal mining
              or identify any specific chemical contaminant.
            </p>
          </div>
        </Panel>
      </div>
    </>
  );
}

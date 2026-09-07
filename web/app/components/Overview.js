"use client";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { IconDrop, IconPin, IconRain, IconSpark, IconWarn } from "./Icons";
import { Empty, Indicator, Kpi, Note, Panel, Severity } from "./Ui";
import { IndicatorTrend, RainfallVsIndicator } from "./Charts";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div style={{ height: 460, borderRadius: 12, background: "var(--bg)" }} />,
});

const SEV_COLOR = {
  CRITICAL: "var(--critical)", HIGH: "var(--high)", ELEVATED: "var(--elevated)",
  WATCH: "var(--watch)", NORMAL: "var(--normal)", NO_DATA: "var(--nodata)",
};

function fmtDate(s) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("en-GB",
    { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export default function Overview({ summary, stations, series, alerts, river }) {
  const withData = stations.filter((s) => s.observations > 0);
  const [selected, setSelected] = useState(
    withData.find((s) => s.role === "intake")?.id || withData[0]?.id || null
  );
  const station = stations.find((s) => s.id === selected) || withData[0];
  const rows = useMemo(() => (series?.[station?.id] || []).slice(-120), [series, station]);

  const feed = (alerts?.alerts || []).slice(0, 4);
  const detailed = alerts?.detailed || [];
  const lastObs = summary?.latest_observation;
  const ageDays = lastObs
    ? Math.floor((Date.now() - new Date(lastObs).getTime()) / 86400000)
    : null;
  const fresh = ageDays != null && ageDays <= 14;

  if (!summary) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1>Pra River Monitoring Dashboard</h1>
            <p className="subtitle">Satellite-driven insights for cleaner, safer rivers</p>
          </div>
        </div>
        <Panel title="No data yet">
          <Empty>
            The pipeline has not produced a dataset. Run the data workflow, or
            wait for the scheduled run to complete.
          </Empty>
        </Panel>
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pra River Monitoring Dashboard</h1>
          <p className="subtitle">Satellite-driven insights for cleaner, safer rivers</p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="live">
            <span className={`dot ${fresh ? "" : "stale"}`} />
            {fresh ? "Live data" : "Awaiting new pass"}
          </div>
          <div className="live-sub">
            Latest observation {fmtDate(lastObs)}
            {ageDays != null && <> · {ageDays} day{ageDays === 1 ? "" : "s"} ago</>}
          </div>
        </div>
      </div>

      <div className="kpis">
        <Kpi label={`Mean ${summary.indicator.short} (network)`}
             value={summary.mean_indicator != null ? summary.mean_indicator.toFixed(3) : null}
             sub={summary.indicator.name} icon={<IconDrop />} tint="var(--accent)" />
        <Kpi label="Rainfall (7-day mean)" value={summary.mean_rain_7d_mm} unit="mm"
             sub="Across all stations" icon={<IconRain />} tint="#0891b2" />
        <Kpi label="Active alerts" value={summary.active_alerts}
             sub={`${summary.alerts_by_severity?.CRITICAL || 0} critical · ${summary.alerts_by_severity?.HIGH || 0} high`}
             icon={<IconWarn />} tint="var(--critical)" />
        <Kpi label="Monitored locations" value={summary.stations_with_data}
             sub={`of ${summary.stations_total} on the Pra`} icon={<IconPin />} tint="var(--normal)" />
      </div>

      <div className="grid-main">
        <Panel title="Pra River — monitoring network"
               sub={`${summary.indicator.name}, latest status per station`}
               bodyStyle={{ padding: 12 }}>
          <MapView stations={stations} river={river} selected={selected}
                   onSelect={setSelected} height={460} />
        </Panel>

        <div style={{ display: "grid", gap: 16 }}>
          <Panel title="Latest alerts" bodyStyle={{ padding: 0 }}>
            {feed.length === 0 ? (
              <Empty>No alerts. All stations within expected conditions.</Empty>
            ) : feed.map((a, i) => (
              <div className="alert-item" key={i}>
                <span className="alert-bar" style={{ background: SEV_COLOR[a.severity] }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="alert-title">{a.station_name}</div>
                  <div className="alert-meta">{a.station_id} · {a.date}</div>
                  <div className="alert-note">
                    {a.z_score != null
                      ? `${a.z_score.toFixed(1)}σ above expected`
                      : "flagged by anomaly detector"}
                    {a.rain_7d != null && ` · ${a.rain_7d.toFixed(0)} mm rain (7d)`}
                  </div>
                </div>
                <div className="alert-val">
                  <Severity value={a.severity} />
                  <div style={{ fontSize: 13, marginTop: 4, fontWeight: 600 }}>
                    <Indicator value={a.indicator} />
                  </div>
                </div>
              </div>
            ))}
          </Panel>

          <Panel title="Recent observations" bodyStyle={{ padding: 0 }}>
            <div className="tbl-wrap">
              <table>
                <caption className="sr-only">
                  Latest satellite observation for each monitoring station
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Location</th>
                    <th scope="col" className="num">{summary.indicator.short}</th>
                    <th scope="col" className="num">vs expected</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {stations.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <button className="btn"
                                style={{ border: 0, background: "none", padding: 0, textAlign: "left", fontWeight: 500 }}
                                onClick={() => setSelected(s.id)}>
                          {s.name}
                        </button>
                        <div style={{ color: "var(--faint)", fontSize: 11.5 }}>
                          {s.id} · {s.role}
                        </div>
                      </td>
                      <td className="num">
                        {s.latest ? <Indicator value={s.latest.indicator} /> : "—"}
                      </td>
                      <td className="num">
                        {s.latest?.z_score != null ? (
                          <span className={s.latest.z_score > 0 ? "up" : "down"}>
                            {s.latest.z_score > 0 ? "+" : ""}{s.latest.z_score.toFixed(1)}σ
                          </span>
                        ) : "—"}
                      </td>
                      <td><Severity value={s.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid-2">
        <Panel title={`Trend — ${station?.name || ""}`}
               sub="Observed index against the model's expected value">
          {rows.length ? <IndicatorTrend data={rows} /> : <Empty>No observations.</Empty>}
        </Panel>
        <Panel title="Rainfall vs sediment index"
               sub="Does rain explain the change?">
          {rows.length ? <RainfallVsIndicator data={rows} /> : <Empty>No observations.</Empty>}
        </Panel>
      </div>

      <div style={{ marginTop: 16, display: "grid", gap: 16 }}>
        {detailed.length > 0 && (
          <Panel title="Assessment detail" sub="Most recent non-normal assessment per station">
            {detailed.slice(0, 3).map((d, i) => (
              <div key={i} style={{ marginBottom: i === detailed.length - 1 ? 0 : 16 }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <Severity value={d.severity} />
                  <strong style={{ fontSize: 13.5 }}>{d.headline}</strong>
                  <span style={{ color: "var(--faint)", fontSize: 12 }}>
                    confidence: {d.confidence}
                  </span>
                </div>
                <p style={{ color: "var(--muted)", fontSize: 13, margin: "7px 0 0" }}>
                  {d.explanation}
                </p>
                <p style={{ fontSize: 13, margin: "6px 0 0" }}>
                  <strong>Recommended:</strong>{" "}
                  <span style={{ color: "var(--muted)" }}>{d.recommended_action}</span>
                </p>
              </div>
            ))}
          </Panel>
        )}
        <Note>
          <strong>What this system does.</strong> It detects unusual
          satellite-observed river and sediment conditions and weighs them
          against rainfall, season and upstream stations. It reports the{" "}
          <strong>{summary.indicator.name}</strong> — {summary.indicator.note}{" "}
          It does not confirm a cause, and it does not detect mining or any
          specific contaminant.
        </Note>
      </div>
    </>
  );
}

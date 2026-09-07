"use client";
import { useMemo, useState } from "react";
import { Empty, Indicator, Note, Panel, Severity } from "./Ui";

const SEVERITIES = ["CRITICAL", "HIGH", "ELEVATED", "WATCH"];
const SEV_COLOR = {
  CRITICAL: "var(--critical)", HIGH: "var(--high)",
  ELEVATED: "var(--elevated)", WATCH: "var(--watch)",
};

export default function Alerts({ alerts, stations }) {
  const all = alerts?.alerts || [];
  const detailed = alerts?.detailed || [];
  const detailByKey = useMemo(() => {
    const m = new Map();
    detailed.forEach((d) => m.set(`${d.station_id}|${d.date}`, d));
    return m;
  }, [detailed]);

  const [sev, setSev] = useState("ALL");
  const [station, setStation] = useState("ALL");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const filtered = useMemo(() => all.filter((a) => {
    if (sev !== "ALL" && a.severity !== sev) return false;
    if (station !== "ALL" && a.station_id !== station) return false;
    if (from && a.date < from) return false;
    if (to && a.date > to) return false;
    return true;
  }), [all, sev, station, from, to]);

  const counts = SEVERITIES.reduce((acc, s) => {
    acc[s] = all.filter((a) => a.severity === s).length;
    return acc;
  }, {});

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Alerts</h1>
          <p className="subtitle">
            Every non-normal assessment, newest first. {all.length} total.
          </p>
        </div>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        {SEVERITIES.map((s) => (
          <div className="kpi" key={s} style={{ alignItems: "center" }}>
            <span className="kpi-icon" style={{
              background: `color-mix(in srgb, ${SEV_COLOR[s]} 16%, transparent)`,
              color: SEV_COLOR[s], fontWeight: 800, fontSize: 13 }}>
              {counts[s]}
            </span>
            <span>
              <span className="kpi-label">{s}</span>
              <div className="kpi-sub">
                {s === "CRITICAL" && "Extreme, corroborated"}
                {s === "HIGH" && "Strong, persistent"}
                {s === "ELEVATED" && "Needs attention"}
                {s === "WATCH" && "Weak or short-lived"}
              </div>
            </span>
          </div>
        ))}
      </div>

      <Panel
        title="Filter"
        bodyStyle={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}
      >
        <div>
          <label htmlFor="f-sev" className="kpi-label">Severity</label><br />
          <select id="f-sev" value={sev} onChange={(e) => setSev(e.target.value)}>
            <option value="ALL">All severities</option>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="f-station" className="kpi-label">Location</label><br />
          <select id="f-station" value={station} onChange={(e) => setStation(e.target.value)}>
            <option value="ALL">All locations</option>
            {stations.map((s) => <option key={s.id} value={s.id}>{s.id} — {s.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="f-from" className="kpi-label">From</label><br />
          <input id="f-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div>
          <label htmlFor="f-to" className="kpi-label">To</label><br />
          <input id="f-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <button className="btn" onClick={() => { setSev("ALL"); setStation("ALL"); setFrom(""); setTo(""); }}>
          Reset
        </button>
        <span style={{ color: "var(--muted)", fontSize: 13, marginLeft: "auto" }}>
          {filtered.length} shown
        </span>
      </Panel>

      <div style={{ marginTop: 16 }}>
        <Panel title="Alert history" bodyStyle={{ padding: 0 }}>
          {filtered.length === 0 ? (
            <Empty>No alerts match these filters.</Empty>
          ) : filtered.slice(0, 300).map((a, i) => {
            const d = detailByKey.get(`${a.station_id}|${a.date}`);
            return (
              <div className="alert-item" key={i}>
                <span className="alert-bar" style={{ background: SEV_COLOR[a.severity] }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: "flex", gap: 9, alignItems: "center", flexWrap: "wrap" }}>
                    <Severity value={a.severity} />
                    <span className="alert-title">{a.station_name}</span>
                    <span className="alert-meta">{a.station_id} · {a.date}</span>
                  </div>
                  <div className="alert-note">
                    Index <Indicator value={a.indicator} />
                    {a.expected != null && <> · expected <Indicator value={a.expected} /></>}
                    {a.z_score != null && <> · {a.z_score.toFixed(1)}σ deviation</>}
                    {a.rain_7d != null && <> · {a.rain_7d.toFixed(0)} mm rain (7d)</>}
                    {a.quality && <> · quality {a.quality}</>}
                  </div>
                  {d && (
                    <details style={{ marginTop: 7 }}>
                      <summary style={{ cursor: "pointer", fontSize: 12.5, color: "var(--accent)" }}>
                        Why this was raised
                      </summary>
                      <p style={{ color: "var(--muted)", fontSize: 12.5, margin: "7px 0 0" }}>
                        {d.explanation}
                      </p>
                      {d.signals?.length > 0 && (
                        <ul style={{ color: "var(--muted)", fontSize: 12.5, margin: "7px 0 0", paddingLeft: 18 }}>
                          {d.signals.map((s, j) => <li key={j}>{s}</li>)}
                        </ul>
                      )}
                      <p style={{ fontSize: 12.5, margin: "7px 0 0" }}>
                        <strong>Recommended:</strong>{" "}
                        <span style={{ color: "var(--muted)" }}>{d.recommended_action}</span>
                      </p>
                    </details>
                  )}
                </div>
              </div>
            );
          })}
        </Panel>
      </div>

      <div style={{ marginTop: 16 }}>
        <Note>
          An alert means the satellite-observed river condition is unusual for
          the season, the rainfall and the upstream state — nothing more. It is a
          prompt to investigate, not evidence of mining or of any specific
          pollutant.
        </Note>
      </div>
    </>
  );
}

"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Scatter, ComposedChart, Tooltip, XAxis, YAxis,
} from "recharts";

const TIER_COLOR = {
  ALERT: "var(--alert)",
  ELEVATED: "var(--elevated)",
  NORMAL: "var(--normal)",
  CONTROL: "var(--control)",
};

function latestTier(point, alerts) {
  if (point.role === "control") return "CONTROL";
  const mine = alerts.filter((a) => a.point === point.name);
  return mine.length ? mine[0].tier : "NORMAL";
}

export default function Dashboard({ data }) {
  const points = data.points || [];
  const alerts = data.alerts || [];
  const monitored = points.filter((p) => p.role !== "control");
  const [selected, setSelected] = useState(
    (monitored[0] || points[0] || {}).id || null
  );

  const point = points.find((p) => p.id === selected) || points[0];
  const control = points.find((p) => p.role === "control");

  // merge the selected point's series with the control's, keyed by date, so the
  // control can be drawn as a reference line under the monitored point
  const series = useMemo(() => {
    if (!point) return [];
    const byDate = new Map();
    for (const r of point.readings || []) {
      byDate.set(r.date, { date: r.date, ndti: r.ndti, pixels: r.pixels });
    }
    for (const r of control?.readings || []) {
      const row = byDate.get(r.date) || { date: r.date };
      row.control = r.ndti;
      byDate.set(r.date, row);
    }
    const flagged = new Set((point.anomalies || []).map((a) => a.date));
    return [...byDate.values()]
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((r) => ({ ...r, anomaly: flagged.has(r.date) ? r.ndti : null }));
  }, [point, control]);

  if (!points.length) {
    return (
      <main className="wrap">
        <h1>Pra River Early Warning</h1>
        <p className="sub">
          No data yet — the pipeline has not written a snapshot.
        </p>
      </main>
    );
  }

  return (
    <main className="wrap">
      <h1>Pra River Early Warning</h1>
      <p className="sub">
        Satellite turbidity monitoring for galamsey-driven pollution, Pra basin,
        Ghana.{" "}
        {data.generated_at && <>Last updated {data.generated_at.slice(0, 10)}.</>}
      </p>

      <div className="cards">
        {points.map((p) => {
          const tier = latestTier(p, alerts);
          const last = (p.readings || []).slice(-1)[0];
          return (
            <button
              key={p.id}
              className="card"
              style={{ "--c": TIER_COLOR[tier] }}
              aria-pressed={p.id === selected}
              onClick={() => setSelected(p.id)}
            >
              <div className="role">{p.role}</div>
              <div className="name">{p.name}</div>
              <span className="tier" style={{ "--c": TIER_COLOR[tier] }}>
                {tier}
              </span>
              <div className="val">
                {last ? last.ndti.toFixed(3) : "—"}
                <span className="meta"> NDTI</span>
              </div>
              <div className="meta">
                {last
                  ? `${last.date} · ${last.pixels} water px · ${p.readings.length} readings`
                  : "no readings"}
              </div>
            </button>
          );
        })}
      </div>

      <h2>Turbidity over time — {point.name}</h2>
      <div className="panel chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date" tick={{ fontSize: 11, fill: "var(--muted)" }}
              stroke="var(--border)" minTickGap={40}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--muted)" }}
              stroke="var(--border)" width={56}
              label={{ value: "NDTI", angle: -90, position: "insideLeft",
                       fill: "var(--muted)", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)",
                              borderRadius: 8, color: "var(--text)", fontSize: 13 }}
              formatter={(v, n) => [typeof v === "number" ? v.toFixed(4) : v, n]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone" dataKey="control" name="Control (upstream)"
              stroke="var(--control)" strokeDasharray="5 4" strokeWidth={1.5}
              dot={false} connectNulls
            />
            <Line
              type="monotone" dataKey="ndti" name={point.name}
              stroke="var(--accent)" strokeWidth={2} dot={{ r: 2 }} connectNulls
            />
            <Scatter dataKey="anomaly" name="Flagged anomaly" fill="var(--alert)" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <h2>Alerts</h2>
      {alerts.length === 0 ? (
        <p className="empty">
          No alerts recorded yet. The scheduled job writes one entry per scored
          reading.
        </p>
      ) : (
        <div className="feed">
          {alerts.slice(0, 25).map((a, i) => (
            <div key={i} className="item" style={{ "--c": TIER_COLOR[a.tier] }}>
              <div className="when">
                {a.date} · {a.point}
              </div>
              <div>{a.text}</div>
            </div>
          ))}
        </div>
      )}

      <h2>How the model decides what is normal</h2>
      <div className="panel">
        {point.model ? (
          <>
            <dl className="kv">
              <dt>Algorithm</dt>
              <dd>Isolation Forest (scikit-learn), unsupervised</dd>
              <dt>Trees</dt>
              <dd>{point.model.trees}</dd>
              <dt>Trained on</dt>
              <dd>{point.model.samples} historical readings at this point</dd>
              <dt>Contamination</dt>
              <dd>{point.model.contamination}</dd>
              <dt>Flagged</dt>
              <dd>{(point.anomalies || []).length} historical readings</dd>
            </dl>
            <p className="sub" style={{ margin: "14px 0 6px" }}>
              The 7 features each reading is judged on:
            </p>
            <div className="chips">
              {point.model.features.map((f) => (
                <span key={f} className="chip">{f}</span>
              ))}
            </div>
            <p className="meta" style={{ color: "var(--muted)", fontSize: 13, marginTop: 14 }}>
              The model is never told what pollution looks like. It learns the
              normal range of turbidity at this point across seasons, then scores
              how far each new reading sits from that. The last two features carry
              the upstream control: when rain lifts every point together, the
              combination is familiar and scores as normal — a rise here{" "}
              <em>without</em> one upstream is the rare pattern.
            </p>
          </>
        ) : (
          <p className="empty">
            No trained model for this point yet
            {point.role === "control" && " — the control point is a reference, not a monitored point"}.
          </p>
        )}
      </div>
    </main>
  );
}

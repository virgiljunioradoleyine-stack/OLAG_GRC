"use client";
import {
  Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from "recharts";

const AXIS = { fontSize: 11, fill: "var(--muted)" };
const TIP = {
  background: "var(--panel)", border: "1px solid var(--border)",
  borderRadius: 8, color: "var(--text)", fontSize: 12.5,
};

const fmt = (v) => (typeof v === "number" ? v.toFixed(3) : v);

/** Indicator against the model's expected value, with anomalies marked. */
export function IndicatorTrend({ data, height = 300, showExpected = true }) {
  const withBand = data.map((d) => ({
    ...d,
    anomalyPoint: d.anomaly ? d.indicator : null,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={withBand} margin={{ top: 8, right: 10, bottom: 2, left: -14 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="date" tick={AXIS} stroke="var(--border)" minTickGap={44} />
        <YAxis tick={AXIS} stroke="var(--border)" width={54} />
        <Tooltip contentStyle={TIP} formatter={(v, n) => [fmt(v), n]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {showExpected && (
          <Line type="monotone" dataKey="expected" name="Expected (model)"
                stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="5 4"
                dot={false} connectNulls isAnimationActive={false} />
        )}
        <Line type="monotone" dataKey="indicator" name="Observed index"
              stroke="var(--accent)" strokeWidth={2} dot={{ r: 1.6 }}
              connectNulls isAnimationActive={false} />
        <Scatter dataKey="anomalyPoint" name="Flagged" fill="var(--critical)" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Rainfall bars against the indicator — the visual form of the core question. */
export function RainfallVsIndicator({ data, height = 300 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 6, bottom: 2, left: -14 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="date" tick={AXIS} stroke="var(--border)" minTickGap={44} />
        <YAxis yAxisId="rain" tick={AXIS} stroke="var(--border)" width={44}
               label={{ value: "mm", angle: -90, position: "insideLeft", ...AXIS }} />
        <YAxis yAxisId="idx" orientation="right" tick={AXIS} stroke="var(--border)" width={52} />
        <Tooltip contentStyle={TIP} formatter={(v, n) => [fmt(v), n]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar yAxisId="rain" dataKey="rain_7d" name="Rainfall, 7-day (mm)"
             fill="var(--accent)" opacity={0.35} isAnimationActive={false} />
        <Line yAxisId="idx" type="monotone" dataKey="indicator" name="Sediment index"
              stroke="var(--high)" strokeWidth={2} dot={false}
              connectNulls isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Compare several stations on one axis. */
export function StationCompare({ data, keys, height = 300 }) {
  const colors = ["var(--accent)", "var(--high)", "var(--normal)", "var(--critical)",
                  "var(--watch)", "#8b5cf6", "#0891b2", "#be185d"];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 10, bottom: 2, left: -14 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="date" tick={AXIS} stroke="var(--border)" minTickGap={44} />
        <YAxis tick={AXIS} stroke="var(--border)" width={54} />
        <Tooltip contentStyle={TIP} formatter={(v, n) => [fmt(v), n]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {keys.map((k, i) => (
          <Line key={k} type="monotone" dataKey={k} name={k}
                stroke={colors[i % colors.length]} strokeWidth={1.8}
                dot={false} connectNulls isAnimationActive={false} />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Deviation from expected, in robust standard deviations. */
export function ZScoreChart({ data, height = 260 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 10, bottom: 2, left: -14 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="date" tick={AXIS} stroke="var(--border)" minTickGap={44} />
        <YAxis tick={AXIS} stroke="var(--border)" width={44} />
        <Tooltip contentStyle={TIP} formatter={(v, n) => [fmt(v), n]} />
        <Bar dataKey="z_score" name="Deviation (σ)" fill="var(--elevated)"
             isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

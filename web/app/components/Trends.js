"use client";
import { useMemo, useState } from "react";
import { Empty, Panel } from "./Ui";
import { IndicatorTrend, RainfallVsIndicator, StationCompare, ZScoreChart } from "./Charts";

const RANGES = [
  { key: "7d", label: "7 days", days: 7 },
  { key: "30d", label: "30 days", days: 30 },
  { key: "90d", label: "90 days", days: 90 },
  { key: "1y", label: "1 year", days: 365 },
  { key: "all", label: "All", days: null },
];

function within(rows, days) {
  if (!days) return rows;
  const cut = Date.now() - days * 86400000;
  return rows.filter((r) => new Date(r.date).getTime() >= cut);
}

export default function Trends({ stations, series }) {
  const withData = stations.filter((s) => s.observations > 0);
  const [station, setStation] = useState(withData[0]?.id);
  const [range, setRange] = useState("1y");
  const days = RANGES.find((r) => r.key === range)?.days;

  const rows = useMemo(
    () => within(series?.[station] || [], days), [series, station, days]);

  // merge every station onto a shared date axis for comparison
  const compare = useMemo(() => {
    const byDate = new Map();
    withData.forEach((s) => {
      within(series?.[s.id] || [], days).forEach((r) => {
        const e = byDate.get(r.date) || { date: r.date };
        e[s.id] = r.indicator;
        byDate.set(r.date, e);
      });
    });
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [series, withData, days]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data &amp; Trends</h1>
          <p className="subtitle">
            Sediment index, model expectation, rainfall and station comparison
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label className="sr-only" htmlFor="station-select">Station</label>
          <select id="station-select" value={station || ""}
                  onChange={(e) => setStation(e.target.value)}>
            {withData.map((s) => (
              <option key={s.id} value={s.id}>{s.id} — {s.name}</option>
            ))}
          </select>
          <div className="seg" role="group" aria-label="Time range">
            {RANGES.map((r) => (
              <button key={r.key} className="btn" aria-pressed={range === r.key}
                      onClick={() => setRange(r.key)}>{r.label}</button>
            ))}
          </div>
        </div>
      </div>

      {rows.length === 0 ? (
        <Panel><Empty>No observations in this range.</Empty></Panel>
      ) : (
        <>
          <Panel title="Observed index vs expected conditions"
                 sub={`${rows.length} observations · flagged points marked in red`}>
            <IndicatorTrend data={rows} height={330} />
          </Panel>
          <div className="grid-2">
            <Panel title="Rainfall vs sediment index"
                   sub="Rain is the ordinary explanation for a rise">
              <RainfallVsIndicator data={rows} />
            </Panel>
            <Panel title="Deviation from expected"
                   sub="Positive bars are dirtier than the model expects">
              <ZScoreChart data={rows} />
            </Panel>
          </div>
          <div style={{ marginTop: 16 }}>
            <Panel title="All stations compared"
                   sub="Upstream stations should lead downstream ones during a real event">
              {compare.length
                ? <StationCompare data={compare} keys={withData.map((s) => s.id)} height={320} />
                : <Empty>Not enough overlapping observations.</Empty>}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}

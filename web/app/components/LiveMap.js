"use client";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Empty, Indicator, Panel, Severity } from "./Ui";
import { IndicatorTrend } from "./Charts";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div style={{ height: 560, borderRadius: 12, background: "var(--bg)" }} />,
});

export default function LiveMap({ stations, series, river, network, candidates }) {
  const withData = stations.filter((s) => s.observations > 0);
  const [selected, setSelected] = useState(withData[0]?.id || stations[0]?.id);
  const [pickMode, setPickMode] = useState(false);
  const [picked, setPicked] = useState(null);
  const [copied, setCopied] = useState(false);
  const s = stations.find((x) => x.id === selected);
  const rows = (series?.[selected] || []).slice(-90);

  const seg = (network?.segments || []).find((x) => x.to === selected);
  const nCand = candidates?.features?.length || 0;

  const nextId = (() => {
    const nums = stations.map((x) => parseInt(String(x.id).replace(/\D/g, ""), 10))
      .filter(Number.isFinite);
    return "P" + String((nums.length ? Math.max(...nums) : 0) + 1).padStart(2, "0");
  })();

  const snippet = picked && !picked.error
    ? `Add a station at ${picked.lat.toFixed(6)}, ${picked.lon.toFixed(6)}`
      + ` (${picked.water_pixels} water pixels, tile ${picked.tile}) as ${nextId}.`
    : "";

  function copy() {
    if (!snippet) return;
    navigator.clipboard?.writeText(snippet).then(
      () => { setCopied(true); setTimeout(() => setCopied(false), 2000); },
      () => {}
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Live Map</h1>
          <p className="subtitle">
            Monitoring network on the Pra, with the river centreline from OpenStreetMap
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn" aria-pressed={pickMode}
                  disabled={!nCand}
                  title={nCand ? `${nCand} verified candidate sites`
                               : "No candidate sites generated yet"}
                  onClick={() => { setPickMode(!pickMode); setPicked(null); }}>
            {pickMode ? "Cancel" : "Pick a new station"}
          </button>
          {nCand > 0 && (
            <span style={{ color: "var(--muted)", fontSize: 12 }}>
              {nCand} verified sites
            </span>
          )}
        </div>
      </div>

      <div className="grid-main">
        <Panel bodyStyle={{ padding: 12 }}>
          {pickMode && (
            <p style={{ margin: "0 0 10px", fontSize: 13, color: "var(--muted)" }}>
              Click anywhere on the river. The click snaps to the nearest
              <strong style={{ color: "var(--text)" }}> verified </strong>
              site — one already checked against the satellite record — so the
              numbers you see are measured, not guessed.
            </p>
          )}
          <MapView stations={stations} river={river} selected={selected}
                   onSelect={setSelected} height={560}
                   candidates={candidates} pickMode={pickMode} onPick={setPicked} />
        </Panel>

        <div style={{ display: "grid", gap: 16 }}>
          {pickMode && (
            <Panel title="Proposed station"
                   sub={picked && !picked.error ? `would become ${nextId}` : null}>
              {!picked ? (
                <Empty>Click the river on the map.</Empty>
              ) : picked.error ? (
                <Empty>{picked.error}</Empty>
              ) : (
                <>
                  <dl className="kv">
                    <dt>Coordinates</dt>
                    <dd>{picked.lat.toFixed(6)}, {picked.lon.toFixed(6)}</dd>
                    <dt>Water pixels</dt>
                    <dd>{picked.water_pixels} in a {s?.radius_m || 500} m window</dd>
                    <dt>Sentinel-2 tile</dt><dd>{picked.tile}</dd>
                    <dt>Snapped</dt><dd>{picked.snapped_m} m from your click</dd>
                  </dl>
                  <p style={{ fontSize: 12.5, color: "var(--muted)", margin: "12px 0 8px" }}>
                    Send this line to add it to the monitoring network:
                  </p>
                  <code style={{
                    display: "block", background: "var(--bg)", padding: "9px 11px",
                    borderRadius: 8, fontSize: 12, lineHeight: 1.5,
                    border: "1px solid var(--border)", wordBreak: "break-word",
                  }}>{snippet}</code>
                  <button className="btn" style={{ marginTop: 10 }} onClick={copy}>
                    {copied ? "Copied" : "Copy"}
                  </button>
                  <p style={{ fontSize: 12, color: "var(--faint)", marginTop: 10 }}>
                    Adding a station re-runs collection for it across the full
                    archive, so its history appears alongside the others.
                  </p>
                </>
              )}
            </Panel>
          )}
          <Panel title={s ? s.name : "Select a station"}
                 sub={s ? `${s.id} · ${s.role}` : null}>
            {!s ? <Empty>Choose a station on the map.</Empty> : (
              <>
                <div style={{ marginBottom: 12 }}><Severity value={s.status} /></div>
                <dl className="kv">
                  <dt>Coordinates</dt>
                  <dd>{s.lat.toFixed(5)}, {s.lon.toFixed(5)}</dd>
                  <dt>Position</dt>
                  <dd>#{s.order} of {stations.length} (upstream → downstream)</dd>
                  <dt>Reading window</dt>
                  <dd>{s.radius_m} m radius (~{(s.radius_m * 2 / 1000).toFixed(1)} km of channel)</dd>
                  <dt>Observations</dt>
                  <dd>{s.observations}</dd>
                  {s.latest && <>
                    <dt>Latest reading</dt><dd>{s.latest.date}</dd>
                    <dt>Sediment index</dt><dd><Indicator value={s.latest.indicator} /></dd>
                    <dt>Expected</dt><dd><Indicator value={s.latest.expected} /></dd>
                    <dt>Deviation</dt>
                    <dd>{s.latest.z_score != null ? `${s.latest.z_score.toFixed(2)}σ` : "—"}</dd>
                    <dt>Rainfall (7d)</dt>
                    <dd>{s.latest.rain_7d != null ? `${s.latest.rain_7d.toFixed(0)} mm (${s.latest.rain_context})` : "—"}</dd>
                    <dt>Data quality</dt><dd>{s.latest.quality}</dd>
                    <dt>Confidence</dt><dd>{s.latest.confidence}</dd>
                  </>}
                  {seg && <>
                    <dt>From {seg.from}</dt>
                    <dd>{(seg.distance_m / 1000).toFixed(1)} km · travel {seg.travel_hours_min}–{seg.travel_hours_max} h</dd>
                  </>}
                </dl>
                {s.description && (
                  <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 12 }}>
                    {s.description}
                  </p>
                )}
              </>
            )}
          </Panel>

          <Panel title="Recent trend" sub="Last 90 observations">
            {rows.length ? <IndicatorTrend data={rows} height={220} />
                         : <Empty>No observations.</Empty>}
          </Panel>
        </div>
      </div>
    </>
  );
}

"use client";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Empty, Indicator, Panel, Severity } from "./Ui";
import { IndicatorTrend } from "./Charts";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div style={{ height: 560, borderRadius: 12, background: "var(--bg)" }} />,
});

export default function LiveMap({ stations, series, river, network }) {
  const withData = stations.filter((s) => s.observations > 0);
  const [selected, setSelected] = useState(withData[0]?.id || stations[0]?.id);
  const s = stations.find((x) => x.id === selected);
  const rows = (series?.[selected] || []).slice(-90);

  const seg = (network?.segments || []).find((x) => x.to === selected);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Live Map</h1>
          <p className="subtitle">
            Monitoring network on the Pra, with the river centreline from OpenStreetMap
          </p>
        </div>
      </div>

      <div className="grid-main">
        <Panel bodyStyle={{ padding: 12 }}>
          <MapView stations={stations} river={river} selected={selected}
                   onSelect={setSelected} height={560} />
        </Panel>

        <div style={{ display: "grid", gap: 16 }}>
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

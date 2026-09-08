"use client";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Empty, Indicator, Panel, Severity } from "./Ui";
import { IndicatorTrend } from "./Charts";

const REPO_URL = "https://github.com/virgiljunioradoleyine-stack/OLAG_GRC";
const FENCE = "```";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div style={{ height: 560, borderRadius: 12, background: "var(--bg)" }} />,
});

export default function LiveMap({ stations, series, river, network, candidates }) {
  const withData = stations.filter((s) => s.observations > 0);
  const [selected, setSelected] = useState(withData[0]?.id || stations[0]?.id);
  const [pickMode, setPickMode] = useState(false);
  const [picked, setPicked] = useState(null);
  const [stationName, setStationName] = useState("");
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(null);
  const [addError, setAddError] = useState(null);
  const [needsKey, setNeedsKey] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [useIssueFallback, setUseIssueFallback] = useState(false);
  const s = stations.find((x) => x.id === selected);
  const rows = (series?.[selected] || []).slice(-90);

  const seg = (network?.segments || []).find((x) => x.to === selected);
  const nCand = candidates?.features?.length || 0;

  const nextId = (() => {
    const nums = stations.map((x) => parseInt(String(x.id).replace(/\D/g, ""), 10))
      .filter(Number.isFinite);
    return "P" + String((nums.length ? Math.max(...nums) : 0) + 1).padStart(2, "0");
  })();

  // The Add button opens a prefilled issue. Opening it triggers the
  // add-station workflow, which validates the point against the published
  // candidates, collects its history and rebuilds the dashboard. GitHub's own
  // login authorises the write, so the site needs no token and no sign-in of
  // its own -- and the page stays a static export.
  const addUrl = (() => {
    if (!picked || picked.error) return null;
    const req = {
      lat: Number(picked.lat.toFixed(6)),
      lon: Number(picked.lon.toFixed(6)),
      name: stationName.trim() || `Pra Reach ${nextId}`,
      role: "monitor",
    };
    const body = [
      `Adding a monitoring station picked on the Live Map.`,
      ``,
      `- **${req.name}** at \`${req.lat}, ${req.lon}\``,
      `- ${picked.water_pixels} usable water pixels, tile \`${picked.tile}\``,
      `- snapped ${picked.snapped_m} m from the click`,
      ``,
      FENCE + "json",
      JSON.stringify(req, null, 2),
      FENCE,
      ``,
      `Submitting this issue runs the add-station workflow. It will comment here`,
      `with the result and close the issue.`,
    ].join("\n");
    return `${REPO_URL}/issues/new?title=${encodeURIComponent(`[station] ${req.name}`)}`
      + `&body=${encodeURIComponent(body)}`;
  })();

  // One click. The route validates the point server-side and opens the
  // tracking issue itself, so the user stays here. If the deployment has no
  // key configured the route says so and we fall back to the GitHub link,
  // which needs no secret -- the feature degrades rather than breaking.
  async function addStation() {
    if (!picked || picked.error) return;
    setAdding(true);
    setAddError(null);
    let stored = "";
    try { stored = window.localStorage.getItem("prw.addKey") || ""; } catch {}
    try {
      const res = await fetch("/api/stations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: picked.lat, lon: picked.lon,
          name: stationName.trim(), key: keyInput || stored,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        try { window.localStorage.setItem("prw.addKey", keyInput || stored); } catch {}
        setAdded(data);
        setNeedsKey(false);
        setKeyInput("");
      } else if (data.fallback === "issue") {
        setUseIssueFallback(true);
      } else if (data.needsKey) {
        setNeedsKey(true);
        setAddError(stored || keyInput ? data.error : null);
      } else {
        setAddError(data.error || `The request failed (${res.status}).`);
      }
    } catch {
      setUseIssueFallback(true);
    } finally {
      setAdding(false);
    }
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
                  <label style={{ display: "block", fontSize: 12.5,
                                  color: "var(--muted)", margin: "14px 0 6px" }}>
                    Name it (optional)
                  </label>
                  <input value={stationName} maxLength={60}
                         onChange={(e) => setStationName(e.target.value)}
                         placeholder={`Pra Reach ${nextId}`}
                         style={{
                           width: "100%", padding: "8px 10px", borderRadius: 8,
                           border: "1px solid var(--border)", background: "var(--bg)",
                           color: "var(--text)", fontSize: 13,
                         }} />

                  {added ? (
                    <div style={{ marginTop: 12 }}>
                      <p style={{ fontSize: 13, margin: "0 0 6px" }}>
                        <strong>{added.id} — {added.name}</strong> is being added.
                      </p>
                      <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
                        Its full Sentinel-2 history is being collected and the
                        dashboard rebuilt. That takes a few minutes.{" "}
                        <a href={added.tracking_url} target="_blank"
                           rel="noopener noreferrer">Follow progress</a>.
                      </p>
                    </div>
                  ) : useIssueFallback ? (
                    <>
                      <a className="btn btn-primary" href={addUrl || "#"}
                         target="_blank" rel="noopener noreferrer"
                         style={{ display: "block", textAlign: "center",
                                  marginTop: 12, textDecoration: "none" }}>
                        Add {nextId} to the network
                      </a>
                      <p style={{ fontSize: 12, color: "var(--faint)", marginTop: 10 }}>
                        One-click adding is not configured on this deployment, so
                        this opens a prefilled request on GitHub instead — your
                        GitHub login is what authorises it. Confirming it does the
                        same work.
                      </p>
                    </>
                  ) : (
                    <>
                      {needsKey && (
                        <>
                          <label style={{ display: "block", fontSize: 12.5,
                                          color: "var(--muted)", margin: "14px 0 6px" }}>
                            Operator key
                          </label>
                          <input type="password" value={keyInput} autoComplete="off"
                                 onChange={(e) => setKeyInput(e.target.value)}
                                 placeholder="asked once, then remembered"
                                 style={{
                                   width: "100%", padding: "8px 10px", borderRadius: 8,
                                   border: "1px solid var(--border)",
                                   background: "var(--bg)", color: "var(--text)",
                                   fontSize: 13,
                                 }} />
                        </>
                      )}
                      <button className="btn btn-primary" onClick={addStation}
                              disabled={adding || (needsKey && !keyInput)}
                              style={{ display: "block", width: "100%",
                                       marginTop: 12 }}>
                        {adding ? "Adding…" : `Add ${nextId} to the network`}
                      </button>
                      {addError && (
                        <p style={{ fontSize: 12.5, color: "var(--critical)",
                                    marginTop: 10 }}>{addError}</p>
                      )}
                      <p style={{ fontSize: 12, color: "var(--faint)", marginTop: 10 }}>
                        This collects the station&apos;s full Sentinel-2 history,
                        rebuilds the dashboard and trains a model, then reports
                        back. Nothing else needs doing.
                      </p>
                    </>
                  )}
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

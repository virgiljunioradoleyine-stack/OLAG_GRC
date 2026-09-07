import { Note, Panel } from "../components/Ui";
import { getAll } from "../lib/data";

export const metadata = { title: "About · Pra River Watch" };

export default function Page() {
  const { summary, stations } = getAll();
  const sources = summary?.data_sources || {};
  const reachable = sources.reachable_anonymously || [];
  const blocked = sources.not_reachable || [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>About &amp; Methodology</h1>
          <p className="subtitle">
            What Pra River Watch measures, how it decides, and what it cannot tell you
          </p>
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Note>
          <strong>Scientific disclaimer.</strong> This system identifies unusual
          river conditions and provides early warnings for investigation. It does
          not independently prove the presence of illegal mining, and it does not
          identify specific chemical contaminants such as mercury or arsenic.
        </Note>
      </div>

      <Panel title="What the system does">
        <div className="prose">
          <p>
            Pra River Watch measures a satellite-derived{" "}
            <strong>{summary?.indicator?.name || "Sediment Anomaly Index"}</strong>{" "}
            at {stations.length} fixed points along Ghana&rsquo;s Pra River, learns what
            is normal for each point in each season given the rainfall, and flags
            departures from that expectation.
          </p>
          <h3>1. Satellite observation</h3>
          <p>
            Sentinel-2 Level-2A scenes are read directly from the public{" "}
            <code>sentinel-cogs</code> bucket on AWS &mdash; no account and no API key.
            Only a ~1 km reach around each station is fetched, using HTTP range
            requests, so a 240 MB scene is never downloaded. Bands used: B04 (red),
            B03 (green), B08 (NIR), B11 (SWIR) and the scene classification layer.
          </p>
          <h3>2. Finding the water</h3>
          <p>
            Water pixels come from a persistent-water mask built with MNDWI across
            many clear dates, restricted to the connected channel the station sits
            on. MNDWI is used rather than the scene classification layer&rsquo;s water
            class because sediment-laden water is spectrally similar to bare soil,
            and the standard water class is therefore blind to exactly the
            condition this project exists to measure.
          </p>
          <h3>3. Environmental context</h3>
          <p>
            Daily rainfall is retrieved per station from NASA POWER, with
            Open-Meteo&rsquo;s ERA5 archive as a fallback. Totals over 1, 3, 7, 14 and
            30 days are computed, together with anomalies against a day-of-year
            climatology built from prior years only. River geometry and place
            names come from OpenStreetMap via the Overpass API.
          </p>
          <h3>4. Expected conditions</h3>
          <p>
            A gradient-boosted regressor predicts what the index should be given
            the season, the recent rainfall, the upstream station and observation
            quality. The residual &mdash; how far reality sits from that expectation &mdash;
            is what the alert engine reasons about. An unsupervised Isolation
            Forest provides an independent second opinion.
          </p>
          <h3>5. Validation</h3>
          <p>
            Models are trained on the earliest period, thresholds are chosen on a
            later validation period, and a final period is held out entirely for
            testing. Nothing is shuffled. All features are strictly
            backward-looking, and an automated test mutates future data to prove
            that no past feature changes as a result.
          </p>
          <h3>6. Alerts</h3>
          <p>
            Severity runs NORMAL → WATCH → ELEVATED → HIGH → CRITICAL. Heavy
            rainfall suppresses severity because it is an ordinary explanation for
            raised sediment; rainfall below its seasonal norm escalates it. A
            single observation cannot reach the top tiers, and a low-quality
            observation cannot raise an alert at all. Alert wording is generated
            from fixed templates &mdash; there is no language model anywhere in the
            system.
          </p>
        </div>
      </Panel>

      <div style={{ marginTop: 16 }}>
        <Panel title="What the system cannot do">
          <div className="prose">
            <ul>
              <li>
                <strong>It cannot measure turbidity in NTU.</strong> No in-situ
                water-quality measurements were obtainable for this basin, so the
                index is uncalibrated. Reporting it as NTU would be fabrication.
              </li>
              <li>
                <strong>It cannot detect mining.</strong> It detects unusual
                surface-water conditions. Many things cause those.
              </li>
              <li>
                <strong>It cannot see through cloud.</strong> The Pra basin is
                heavily clouded; roughly two thirds of scenes are unusable at any
                given point, so observations are irregular.
              </li>
              <li>
                <strong>It cannot warn within hours.</strong> Sentinel-2 revisits
                every five days, and cloud extends that. This system detects
                multi-day episodes and trends.
              </li>
              <li>
                <strong>It cannot identify contaminants.</strong> Mercury, arsenic
                and cyanide are invisible to these instruments.
              </li>
            </ul>
          </div>
        </Panel>
      </div>

      <div style={{ marginTop: 16 }}>
        <Panel title="Data sources"
               sub="All acquired anonymously, verified reachable from CI">
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Source</th><th scope="col">Purpose</th>
                  <th scope="col">Account required</th>
                </tr>
              </thead>
              <tbody>
                {reachable.map((s, i) => (
                  <tr key={i}>
                    <td>{s.name}</td>
                    <td style={{ color: "var(--muted)" }}>{s.note || s.group}</td>
                    <td>No</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {blocked.length > 0 && (
            <>
              <h3 style={{ fontSize: 13.5, margin: "18px 0 8px" }}>
                Sources investigated but unavailable
              </h3>
              <ul style={{ color: "var(--muted)", fontSize: 12.5, paddingLeft: 18 }}>
                {blocked.map((s, i) => <li key={i}><strong>{s.name}</strong> — {s.note}</li>)}
              </ul>
            </>
          )}
        </Panel>
      </div>

      <div style={{ marginTop: 16 }}>
        <Panel title="Attribution">
          <div className="prose">
            <p>
              Contains modified Copernicus Sentinel data, processed by Element 84
              and hosted on the AWS Open Data registry.
              River geometry and place names © OpenStreetMap contributors,
              licensed under the ODbL.
              Rainfall from NASA POWER (NASA Langley Research Center) and the
              Open-Meteo ERA5 archive.
              Basemap imagery © Esri, Maxar and Earthstar Geographics; street
              basemap © OpenStreetMap contributors.
            </p>
          </div>
        </Panel>
      </div>
    </>
  );
}

"use client";
import { useEffect, useMemo, useRef, useState } from "react";

// Centre of the Pra basin, used until the stations can be framed.
const FALLBACK_CENTER = [5.5, -1.6];
const FALLBACK_ZOOM = 9;

// How far a click may be from a verified site before snapping stops being
// helpful. The map has 25 candidates along ~90 km of river, so a click near
// the channel lands within a kilometre or so of one. Beyond this the "nearest"
// site is somewhere the user was not looking -- one real pick snapped 6.5 km
// and offered a stretch of river the user had never pointed at.
const MAX_SNAP_M = 2000;

const SEV_COLOR = {
  CRITICAL: "#dc2626", HIGH: "#ea580c", ELEVATED: "#f59e0b",
  WATCH: "#eab308", NORMAL: "#16a34a", NO_DATA: "#94a3b8",
};

/** Leaflet map of the Pra with the monitoring network.
 *
 *  Basemaps are Esri World Imagery and OpenStreetMap — both usable without an
 *  account, which is why they were chosen (verified reachable from CI; see
 *  data/sources/probe_evidence.json). No key, no billing, nothing for the
 *  operator to configure.
 *
 *  Loaded client-side only: Leaflet touches `window` at import time and would
 *  break the server render.
 */
export default function MapView({
  stations = [], river = null, selected, onSelect, height = 460,
  candidates = null, pickMode = false, onPick = null,
}) {
  const ref = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const [ready, setReady] = useState(false);
  const [layer, setLayer] = useState("satellite");
  const candLayerRef = useRef(null);
  const pickMarkerRef = useRef(null);
  const pickModeRef = useRef(pickMode);
  const onPickRef = useRef(onPick);
  pickModeRef.current = pickMode;
  onPickRef.current = onPick;

  const points = useMemo(
    () => stations.filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lon)),
    [stations]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      await import("leaflet/dist/leaflet.css");
      if (cancelled || !ref.current || mapRef.current) return;

      // The view must be set BEFORE any layer is added. Leaflet cannot project
      // a coordinate without one -- the SVG renderer reads the map's pixel
      // origin on add, and with no view that is undefined, so the first vector
      // layer throws "Cannot read properties of undefined (reading 'min')" and
      // takes the rest of this setup with it. Tile layers survive it because
      // they defer until the map reports loaded, which is why the symptom was
      // a map with imagery and no stations on it rather than a blank panel.
      const map = L.map(ref.current, { scrollWheelZoom: false, zoomControl: true })
        .setView(FALLBACK_CENTER, FALLBACK_ZOOM);
      mapRef.current = map;

      const bases = {
        satellite: L.tileLayer(
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
          { maxZoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" }
        ),
        terrain: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19, attribution: "© OpenStreetMap contributors",
        }),
      };
      bases.satellite.addTo(map);
      map._bases = bases;

      if (river?.features?.length) {
        L.geoJSON(river, {
          style: { color: "#38bdf8", weight: 2.5, opacity: 0.85 },
        }).addTo(map).bindTooltip("Pra River (OpenStreetMap)");
      }

      points.forEach((s) => {
        const color = SEV_COLOR[s.status] || SEV_COLOR.NO_DATA;
        const m = L.circleMarker([s.lat, s.lon], {
          radius: 9, color: "#fff", weight: 2.5,
          fillColor: color, fillOpacity: 1,
        }).addTo(map);
        m.bindTooltip(`${s.id} · ${s.name}`, { direction: "top" });
        m.on("click", () => onSelect && onSelect(s.id));
        markersRef.current[s.id] = m;
      });

      // Click-to-pick. A click cannot verify anything by itself, so it snaps to
      // the nearest pre-verified candidate site rather than reporting wherever
      // the pointer happened to land.
      map.on("click", (e) => {
        if (!pickModeRef.current || !onPickRef.current) return;
        const feats = candidates?.features || [];
        if (!feats.length) {
          onPickRef.current({ error: "No candidate sites have been generated yet." });
          return;
        }
        let best = null, bestD = Infinity;
        for (const f of feats) {
          const [lon, lat] = f.geometry.coordinates;
          const d = map.distance(e.latlng, L.latLng(lat, lon));
          if (d < bestD) { best = f; bestD = d; }
        }
        if (bestD > MAX_SNAP_M) {
          if (pickMarkerRef.current) {
            map.removeLayer(pickMarkerRef.current);
            pickMarkerRef.current = null;
          }
          onPickRef.current({
            error: `No verified site near there — the closest is `
                 + `${(bestD / 1000).toFixed(1)} km away. Click closer to the `
                 + `river, on or near one of the marked sites.`,
          });
          return;
        }
        const [lon, lat] = best.geometry.coordinates;
        if (pickMarkerRef.current) map.removeLayer(pickMarkerRef.current);
        pickMarkerRef.current = L.circleMarker([lat, lon], {
          radius: 11, color: "#1d6feb", weight: 3,
          fillColor: "#1d6feb", fillOpacity: 0.35,
        }).addTo(map);
        onPickRef.current({
          lat, lon,
          water_pixels: best.properties.water_pixels,
          tile: best.properties.tile,
          snapped_m: Math.round(bestD),
          clicked: { lat: e.latlng.lat, lon: e.latlng.lng },
        });
      });

      // Now that the layers exist, frame them.
      if (points.length) {
        map.fitBounds(points.map((s) => [s.lat, s.lon]), { padding: [42, 42] });
      }
      setReady(true);
    })();
    return () => {
      cancelled = true;
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, [points, river, onSelect, candidates]);

  // show or hide the candidate sites when pick mode is toggled
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !mapRef.current) return;
      if (candLayerRef.current) {
        map.removeLayer(candLayerRef.current);
        candLayerRef.current = null;
      }
      if (!pickMode || !candidates?.features?.length) return;
      const group = L.layerGroup();
      candidates.features.forEach((f) => {
        const [lon, lat] = f.geometry.coordinates;
        L.circleMarker([lat, lon], {
          radius: 4, color: "#1d6feb", weight: 1.5,
          fillColor: "#fff", fillOpacity: 0.9,
        })
          .bindTooltip(`${f.properties.water_pixels} water px`, { direction: "top" })
          .addTo(group);
      });
      group.addTo(map);
      candLayerRef.current = group;
    })();
    return () => { cancelled = true; };
  }, [pickMode, candidates, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?._bases) return;
    Object.entries(map._bases).forEach(([k, l]) => {
      if (k === layer) l.addTo(map);
      else map.removeLayer(l);
    });
  }, [layer, ready]);

  useEffect(() => {
    const m = markersRef.current[selected];
    if (m) m.setStyle({ weight: 4, radius: 11 });
    return () => { if (m) m.setStyle({ weight: 2.5, radius: 9 }); };
  }, [selected, ready]);

  return (
    <div style={{ position: "relative" }}>
      <div
        ref={ref}
        role="application"
        aria-label={`Map of ${points.length} monitoring stations on the Pra River`
          + (pickMode ? ". Pick mode is on: click the river to choose a candidate site."
                      : "")}
        style={{
          height, width: "100%", borderRadius: "var(--radius)",
          background: "#0d1420", cursor: pickMode ? "crosshair" : "grab",
        }}
      />
      <div style={{ position: "absolute", top: 10, right: 10, zIndex: 500 }} className="seg">
        {["satellite", "terrain"].map((k) => (
          <button key={k} className="btn" aria-pressed={layer === k}
                  onClick={() => setLayer(k)} style={{ textTransform: "capitalize" }}>
            {k}
          </button>
        ))}
      </div>
      <div style={{
        position: "absolute", bottom: 10, left: 10, zIndex: 500,
        background: "var(--panel)", border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)", padding: "9px 11px", fontSize: 11.5,
        boxShadow: "var(--shadow)",
      }}>
        <div style={{ fontWeight: 650, marginBottom: 5 }}>Station status</div>
        {["CRITICAL", "HIGH", "ELEVATED", "WATCH", "NORMAL", "NO_DATA"].map((k) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: SEV_COLOR[k] }} />
            <span style={{ color: "var(--muted)" }}>{k.replace("_", " ")}</span>
          </div>
        ))}
      </div>
      <p className="sr-only">
        Monitoring stations and their current status:{" "}
        {points.map((s) => `${s.name}: ${s.status || "no data"}`).join("; ")}.
      </p>
    </div>
  );
}

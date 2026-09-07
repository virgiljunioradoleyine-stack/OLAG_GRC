"use client";
import { useEffect, useMemo, useRef, useState } from "react";

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
export default function MapView({ stations = [], river = null, selected, onSelect, height = 460 }) {
  const ref = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const [ready, setReady] = useState(false);
  const [layer, setLayer] = useState("satellite");

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

      const map = L.map(ref.current, { scrollWheelZoom: false, zoomControl: true });
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

      if (points.length) {
        map.fitBounds(points.map((s) => [s.lat, s.lon]), { padding: [42, 42] });
      } else {
        map.setView([5.5, -1.6], 9);
      }
      setReady(true);
    })();
    return () => {
      cancelled = true;
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, [points, river, onSelect]);

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
        style={{ height, width: "100%", borderRadius: "var(--radius)", background: "#0d1420" }}
        role="application"
        aria-label={`Map of ${points.length} monitoring stations on the Pra River`}
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

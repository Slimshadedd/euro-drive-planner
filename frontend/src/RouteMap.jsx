import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap, ZoomControl } from "react-leaflet";

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const darkQuery = typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: dark)") : null;

function useDark() {
  const [dark, setDark] = useState(darkQuery?.matches ?? false);
  useEffect(() => {
    if (!darkQuery) return;
    const on = (e) => setDark(e.matches);
    darkQuery.addEventListener("change", on);
    return () => darkQuery.removeEventListener("change", on);
  }, []);
  return dark;
}

/** Fit the selected route into the part of the map not covered by the floating sheet. */
function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length < 2) return;
    const wide = window.innerWidth > 820;
    map.fitBounds(points, {
      paddingTopLeft: wide ? [450, 40] : [24, 24],
      paddingBottomRight: [40, 40],
      maxZoom: 9,
    });
  }, [map, points]);
  return null;
}

export default function RouteMap({ options, selected, origin, destination, onSelect }) {
  const dark = useDark();
  const sel = options?.[selected];
  const fitPoints = useMemo(() => {
    const pts = sel ? sel.legs.flatMap((l) => l.geometry) : [];
    return pts.length ? pts : [origin, destination].filter(Boolean).map((p) => [p.lat, p.lon]);
  }, [sel, origin, destination]);
  // Re-read colours when the theme flips.
  const c = useMemo(
    () => ({
      road: cssVar("--blue"), sea: cssVar("--teal"), muted: cssVar("--label-3"), bg: cssVar("--bg-2"),
      green: cssVar("--green"), red: cssVar("--red"),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [dark]
  );

  return (
    <div className="map-wrap">
      <MapContainer center={[50.5, 2]} zoom={5} className="map" scrollWheelZoom zoomControl={false}>
        {/* Standard OSM tiles; styles.css softens them, and inverts them into a dark map in dark mode. */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />
        <ZoomControl position="topright" />
        {options?.map((o, i) =>
          i === selected
            ? null
            : o.legs.map((l, j) => (
                <Polyline
                  key={`${i}-${j}`}
                  positions={l.geometry}
                  pathOptions={{ color: c.muted, opacity: 0.6, weight: 4, dashArray: l.type === "crossing" ? "2 8" : null, lineCap: "round" }}
                  eventHandlers={{ click: () => onSelect(i) }}
                />
              ))
        )}
        {sel?.legs.map((l, j) => (
          <Polyline
            key={`casing-${selected}-${j}`}
            positions={l.geometry}
            pathOptions={{ color: dark ? "#000" : "#fff", opacity: l.type === "crossing" ? 0 : 0.9, weight: 9, lineCap: "round" }}
            interactive={false}
          />
        ))}
        {sel?.legs.map((l, j) => (
          <Polyline
            key={`sel-${selected}-${j}`}
            positions={l.geometry}
            pathOptions={{
              color: l.type === "crossing" ? c.sea : c.road,
              opacity: 1,
              weight: l.type === "crossing" ? 4 : 6,
              dashArray: l.type === "crossing" ? "1 9" : null,
              lineCap: "round",
            }}
          >
            <Tooltip sticky>
              {l.type === "crossing" ? `${l.operator}: ${l.from} → ${l.to}` : `Drive ${l.from} → ${l.to}`}
            </Tooltip>
          </Polyline>
        ))}
        {sel?.legs
          .filter((l) => l.type === "crossing")
          .flatMap((l) => [l.geometry[0], l.geometry[1]])
          .map((p, k) => (
            <CircleMarker key={`port-${selected}-${k}`} center={p} radius={5}
              pathOptions={{ color: c.sea, fillColor: c.bg, fillOpacity: 1, weight: 3 }} />
          ))}
        {[origin, destination].filter(Boolean).map((p, k) => (
          <CircleMarker key={`end-${k}-${p.lat}`} center={[p.lat, p.lon]} radius={8}
            pathOptions={{ color: "#fff", fillColor: k ? c.red : c.green, fillOpacity: 1, weight: 3 }}>
            <Tooltip>{k ? "Destination" : "Start"}: {p.short || p.label}</Tooltip>
          </CircleMarker>
        ))}
        <FitBounds points={fitPoints} />
      </MapContainer>
    </div>
  );
}

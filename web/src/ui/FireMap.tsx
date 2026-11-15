import { useEffect, useMemo } from "react";
import { MapContainer, Rectangle, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import { INTENSITY_COLORS, intensityClass } from "./cellActivity";

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [16, 16] });
  }, [map, bounds]);
  return null;
}

export default function FireMap({ cells, resolution, bbox, totals, selectedCell, onSelectCell, sensorColor }: {
  cells: Array<[number, number]>;
  resolution: number;
  bbox: [number, number, number, number];
  totals: Map<number, number>;
  selectedCell: number | null;
  onSelectCell: (index: number | null) => void;
  sensorColor: string;
}) {
  const [west, south, east, north] = bbox;
  const bounds = useMemo<LatLngBoundsExpression>(() => [[south - 0.6, west - 0.6], [north + 0.6, east + 0.6]], [south, west, north, east]);
  const max = Math.max(0, ...totals.values());

  return (
    <MapContainer center={[(south + north) / 2, (west + east) / 2]} zoom={7} scrollWheelZoom className="fire-map" attributionControl>
      <FitBounds bounds={bounds} />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={12}
      />
      <Rectangle bounds={[[south, west], [north, east]]} pathOptions={{ color: sensorColor, weight: 1.5, dashArray: "6 5", fill: false }} interactive={false} />
      {cells.map(([lon, lat], index) => {
        const count = totals.get(index);
        if (!count) return null;
        const selected = selectedCell === index;
        return (
          <Rectangle
            key={index}
            bounds={[[lat, lon], [lat + resolution, lon + resolution]]}
            pathOptions={{
              stroke: selected,
              color: "#ffffff",
              weight: selected ? 2 : 0,
              fillColor: INTENSITY_COLORS[intensityClass(count, max)],
              fillOpacity: 0.68,
            }}
            eventHandlers={{ click: () => onSelectCell(selected ? null : index) }}
          >
            <Tooltip direction="top" sticky>{count.toLocaleString("en-US")} detections · {Math.abs(lat + resolution).toFixed(2)}–{Math.abs(lat).toFixed(2)}° S, {lon.toFixed(2)}–{(lon + resolution).toFixed(2)}° E</Tooltip>
          </Rectangle>
        );
      })}
    </MapContainer>
  );
}

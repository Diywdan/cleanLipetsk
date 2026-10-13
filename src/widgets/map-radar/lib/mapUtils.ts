import type { LatLngBoundsExpression, LatLngTuple } from "leaflet";
import { STATUS_META } from "@/entities/incident/lib/presentation";
import type { IncidentStatus } from "@/entities/incident/types";

// Файл тайлов: вектор OpenStreetMap по Липецкой области (сборка Protomaps, зум до 15).
// CRM отдаёт его по /maps/, на стенде без CRM он лежит в public/maps (как получить — README).
export const MAP_TILES_URL: string =
  import.meta.env.VITE_MAP_TILES_URL || `${import.meta.env.BASE_URL}maps/lipetsk.pmtiles`;

// Липецк целиком, с левым берегом
export const MAP_CENTER: LatLngTuple = [52.611, 39.598];

// Границы вырезки файла тайлов (--bbox=37.6,51.85,40.8,53.75)
export const MAP_BOUNDS: LatLngBoundsExpression = [
  [51.85, 37.6],
  [53.75, 40.8],
];

// В данных координаты [долгота, широта] (как в GeoJSON), Leaflet ждёт [широта, долгота]
export const toLatLng = ([lng, lat]: readonly [number, number] | readonly number[]): LatLngTuple => [lat, lng];

// Маркер обращения: светящаяся точка, у новых и КНМ — пульс.
export function createMarkerElement(
  status: IncidentStatus,
  isSelected: boolean,
  onClick: () => void,
): HTMLDivElement {
  const el = document.createElement("div");
  const color = STATUS_META[status]?.dot ?? "#5C6B7A";
  const base = 14;
  const size = isSelected ? base + 8 : base;

  const ring = isSelected
    ? `border:2px solid #fff;box-shadow:0 0 0 4px color-mix(in srgb, ${color} 35%, transparent), 0 0 22px 4px ${color}`
    : `border:1.5px solid color-mix(in srgb, ${color} 40%, #fff);box-shadow:0 0 14px 2px color-mix(in srgb, ${color} 70%, transparent)`;

  el.style.cssText = [
    `width:${size}px`,
    `height:${size}px`,
    "border-radius:9999px",
    `background:${color}`,
    `color:${color}`,
    ring,
    "transform:translate(-50%,-50%)",
    "cursor:pointer",
    `position:relative;z-index:${isSelected ? 50 : 10}`,
    "transition:width .15s,height .15s,box-shadow .15s",
  ].join(";");
  if (status === "NEW" || status === "KNM_ESCALATION") {
    el.classList.add("marker-pulse");
  }
  el.title = STATUS_META[status]?.label ?? "";

  el.onclick = (e) => {
    e.stopPropagation();
    onClick();
  };

  return el;
}

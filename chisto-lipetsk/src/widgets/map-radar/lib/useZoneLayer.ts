import { useEffect, useState } from 'react';
import L from 'leaflet';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { API_URL, http } from '@/shared/api/http';
import { readThemeColors } from '@/shared/theme/themeColors';
import type { ModeId } from '@/shared/theme/standStore';

// Зона на карте — управа из CRM (GET /upravas/geojson): граница, округ и инженеры,
// закреплённые за ней сегодня. Инженеров заводят в CRM, фронт их только показывает.
interface ZoneProps {
  id: number;
  name: string;
  okrug: string | null;
  territoryId: string;
  engineers: { id: string; name: string }[];
}

type Zones = FeatureCollection<Geometry, ZoneProps>;

// Цвет зоны — по округу; порядок как в нумерации управ (1–3, 4–8, 9–13, 14–19)
const OKRUG_ORDER = ['Левобережный', 'Октябрьский', 'Советский', 'Правобережный'];
const ZONE_VARS = ['zone-1', 'zone-2', 'zone-3', 'zone-4'] as const;

function zoneColor(okrug: string | null): string {
  const index = OKRUG_ORDER.findIndex((name) => okrug?.startsWith(name));
  const colors = readThemeColors();
  return colors[ZONE_VARS[Math.max(index, 0)]];
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
}

function popupHtml(p: ZoneProps): string {
  const engineers = p.engineers.length
    ? p.engineers.map((e) => escapeHtml(e.name)).join('<br>')
    : '<span class="zone-popup-muted">инженер не закреплён</span>';
  return `<div class="zone-popup-title">${escapeHtml(p.name)}</div>`
    + (p.okrug ? `<div class="zone-popup-muted">${escapeHtml(p.okrug)}</div>` : '')
    + `<div class="zone-popup-label">Инженеры</div><div>${engineers}</div>`;
}

// Короткая подпись в центре зоны: «№ 7»; полное название — во всплывающем окне по клику
function shortLabel(p: ZoneProps): string {
  return `№ ${p.id}`;
}

export function useZoneLayer(mapReady: boolean, mapRef: React.RefObject<L.Map | null>, mode: ModeId) {
  const [zones, setZones] = useState<Zones | null>(null);

  // Границы — один раз за сессию; на стенде без бэкенда зон нет
  useEffect(() => {
    if (!API_URL) return;
    let cancelled = false;
    http<Zones>(API_URL, '/upravas/geojson')
      .then((data) => { if (!cancelled) setZones(data); })
      .catch(() => { /* без зон карта работает как раньше */ });
    return () => { cancelled = true; };
  }, []);

  // Перерисовка при смене темы: цвета зон берутся из CSS-переменных темы
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !zones?.features.length) return;

    const layer = L.geoJSON(zones, {
      style: (feature) => {
        const color = zoneColor((feature as Feature<Geometry, ZoneProps>).properties.okrug);
        return { color, weight: 1.2, opacity: 0.75, fillColor: color, fillOpacity: 0.07 };
      },
      onEachFeature: (feature, zone) => {
        const props = (feature as Feature<Geometry, ZoneProps>).properties;
        zone.bindPopup(popupHtml(props), { className: 'zone-popup', closeButton: false, autoPan: false });
        zone.bindTooltip(shortLabel(props), {
          permanent: true, direction: 'center', className: 'zone-label', interactive: false,
        });
        zone.on('mouseover', () => (zone as L.Path).setStyle({ weight: 2.2, fillOpacity: 0.13 }));
        zone.on('mouseout', () => layer.resetStyle(zone));
      },
    }).addTo(map);
    layer.bringToBack(); // метки обращений — в своей панели поверх, а зоны ниже всех векторов

    return () => {
      layer.remove();
    };
  }, [mapReady, zones, mapRef, mode]);
}

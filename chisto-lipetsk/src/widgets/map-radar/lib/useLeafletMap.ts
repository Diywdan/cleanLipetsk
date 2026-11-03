import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import L from 'leaflet';
import { leafletLayer } from 'protomaps-leaflet';
import { LIPETSK_POLYGONS } from './lipetskPolygons';
import { MAP_BOUNDS, MAP_CENTER, MAP_TILES_URL, toLatLng } from './mapUtils';
import { readThemeColors } from '@/shared/theme/themeColors';
import type { ModeId } from '@/shared/theme/standStore';

// protomaps-leaflet строит свой слой от глобального L
Object.assign(window, { L });

interface UseLeafletMapResult {
  mapReady: boolean;
  // Файла подложки нет — карта работает, но без улиц
  tilesMissing: string | null;
  mapRef: RefObject<L.Map | null>;
}

/**
 * Карта на Leaflet с подложкой из своего файла тайлов (вектор OpenStreetMap, Липецкая область).
 * Ни ключа, ни запросов к чужим серверам: файл отдаёт тот же сервер, что и фронт.
 */
export function useLeafletMap(mapContainerRef: RefObject<HTMLDivElement | null>, mode: ModeId): UseLeafletMapResult {
  const [mapReady, setMapReady] = useState(false);
  const [tilesMissing, setTilesMissing] = useState<string | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const zonesRef = useRef<L.Polygon[]>([]);

  useEffect(() => {
    const container = mapContainerRef.current;
    if (!container) return;
    let cancelled = false;

    const map = L.map(container, {
      center: MAP_CENTER,
      zoom: 12,
      zoomSnap: 1,
      zoomDelta: 1,
      minZoom: 10,
      maxZoom: 18,
      // Файл тайлов покрывает только область — дальше карту не уводим
      maxBounds: MAP_BOUNDS,
      maxBoundsViscosity: 1.0,
      zoomControl: false,
    });

    map.attributionControl.setPrefix(
      '<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a> · <a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a>',
    );

    // Зоны ответственности УК; цвета ставит тема (эффект ниже)
    zonesRef.current = LIPETSK_POLYGONS.map((poly) =>
      L.polygon(poly.coordinates.map((ring) => ring.map((point) => toLatLng(point))), {
        color: poly.borderColor,
        weight: 1.5,
        fillOpacity: 0.14,
        interactive: false,
      }).addTo(map),
    );

    // Раскладка меняет размер карты (карточка дела, мобильный вид) — Leaflet об этом сам не узнаёт
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(container);

    // Без файла подложки слой молча рисует пустоту — проверяем, что файл на месте
    fetch(MAP_TILES_URL, { method: 'HEAD' })
      .then((r) => {
        if (!cancelled && !r.ok) setTilesMissing(`${MAP_TILES_URL}, ответ ${r.status}`);
      })
      .catch(() => {
        if (!cancelled) setTilesMissing(`${MAP_TILES_URL}, сервер не ответил`);
      });

    mapRef.current = map;
    map.whenReady(() => {
      if (!cancelled) setMapReady(true);
    });

    return () => {
      cancelled = true;
      resize.disconnect();
      setMapReady(false);
      map.remove();
      mapRef.current = null;
      zonesRef.current = [];
    };
  }, [mapContainerRef]);

  // Тема: подложка своего тона (инверсия светлой красит парки в бурый) и цвета зон.
  // Карту не пересоздаём — вид и масштаб остаются, где их оставил инспектор.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Тон подложки дотягивает CSS-фильтр .map-base canvas (styles/themes.css); маркеры — DOM, их фильтр не трогает
    const base = leafletLayer({
      url: MAP_TILES_URL,
      flavor: mode === 'light' ? 'light' : 'dark',
      lang: 'ru',
      maxDataZoom: 13,
      paintRules: [],
      attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">участники OpenStreetMap</a>',
    });
    base.addTo(map);
    base.bringToBack();

    const theme = readThemeColors();
    const zoneColors = [theme['zone-1'], theme['zone-2']];
    zonesRef.current.forEach((zone, index) => {
      const color = zoneColors[index % zoneColors.length] || LIPETSK_POLYGONS[index].borderColor;
      zone.setStyle({ color, fillColor: color });
    });

    return () => {
      base.remove();
    };
  }, [mode]);

  return { mapReady, tilesMissing, mapRef };
}

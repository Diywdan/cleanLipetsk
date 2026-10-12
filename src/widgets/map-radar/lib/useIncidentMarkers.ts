import { useEffect, useRef } from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useFilteredIncidents } from '@/entities/incident/model/filterStore';
import { useStandStore } from '@/shared/theme/standStore';
import { createMarkerElement } from './mapUtils';

export function useIncidentMarkers(mapReady: boolean, mapRef: React.RefObject<any | null>) {
  const markerChildrenRef = useRef<any[]>([]);

  // На карте — те же обращения, что в реестре после фильтров
  const incidents = useFilteredIncidents();
  const { selectedIncident, selectIncident } = useIncidentStore();
  const theme = useStandStore((s) => s.theme);

  useEffect(() => {
    // Если карта еще не проинициализирована хуком useYandexMap — ничего не делаем
    if (!mapReady || !mapRef.current || !window.ymaps3) return;

    const { YMapMarker } = window.ymaps3;
    const currentMap = mapRef.current;

    // Безопасно очищаем старые маркеры перед перерисовкой
    markerChildrenRef.current.forEach((marker) => {
      try { currentMap.removeChild(marker); } catch { /* ignore */ }
    });
    markerChildrenRef.current = [];

    // Выбранный — последним, чтобы лежал поверх соседей
    const ordered = [...incidents].sort(
      (a, b) => Number(a.id === selectedIncident?.id) - Number(b.id === selectedIncident?.id),
    );

    ordered.forEach((incident) => {
      const isSelected = selectedIncident?.id === incident.id;
      const markerElement = createMarkerElement(
        incident.status,
        isSelected,
        () => selectIncident(incident.id),
        theme,
      );

      const marker = new YMapMarker({
        coordinates: [...incident.location.coordinates],
        draggable: false,
        zIndex: isSelected ? 1000 : 1,
      }, markerElement);

      currentMap.addChild(marker);
      markerChildrenRef.current.push(marker);
    });
  }, [mapReady, incidents, selectedIncident, selectIncident, mapRef, theme]);

  // Перелёт к выбранному обращению
  const selectedId = selectedIncident?.id;
  const selectedCoords = selectedIncident?.location.coordinates;
  useEffect(() => {
    if (!mapReady || !mapRef.current || !selectedCoords) return;
    try {
      const zoom = Math.max(mapRef.current.zoom ?? 14, 14.5);
      mapRef.current.update({ location: { center: [...selectedCoords], zoom, duration: 700 } });
    } catch { /* карта могла быть уничтожена при смене темы */ }
    // координаты меняются вместе с id
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, selectedId, mapRef]);
}

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useFilteredIncidents } from '@/entities/incident/model/filterStore';
import { useStandStore } from '@/shared/theme/standStore';
import { createMarkerElement, toLatLng } from './mapUtils';

export function useIncidentMarkers(mapReady: boolean, mapRef: React.RefObject<L.Map | null>) {
  const markersRef = useRef<L.Marker[]>([]);

  // На карте — те же обращения, что в реестре после фильтров
  const incidents = useFilteredIncidents();
  const { selectedIncident, selectIncident } = useIncidentStore();
  const mode = useStandStore((s) => s.mode);

  useEffect(() => {
    // Если карта еще не проинициализирована хуком useLeafletMap — ничего не делаем
    const currentMap = mapRef.current;
    if (!mapReady || !currentMap) return;

    // Безопасно очищаем старые маркеры перед перерисовкой
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

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
      );

      // Точка рисует себя сама и центрируется своим transform — иконке нужен нулевой размер
      const marker = L.marker(toLatLng(incident.location.coordinates), {
        icon: L.divIcon({ html: markerElement, className: 'incident-marker', iconSize: [0, 0] }),
        keyboard: false,
        zIndexOffset: isSelected ? 1000 : 0,
      }).addTo(currentMap);

      markersRef.current.push(marker);
    });
  }, [mapReady, incidents, selectedIncident, selectIncident, mapRef, mode]);

  // Перелёт к выбранному обращению
  const selectedId = selectedIncident?.id;
  const selectedCoords = selectedIncident?.location.coordinates;
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !selectedCoords) return;
    try {
      const zoom = Math.max(map.getZoom(), 14.5);
      map.flyTo(toLatLng(selectedCoords), zoom, { duration: 0.7 });
    } catch { /* карта могла быть уничтожена при смене темы */ }
    // координаты меняются вместе с id
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, selectedId, mapRef]);
}

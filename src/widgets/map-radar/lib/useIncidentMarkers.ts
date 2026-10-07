import { useEffect, useRef } from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { createMarkerElement } from './mapUtils';

export function useIncidentMarkers(mapReady: boolean, mapRef: React.RefObject<any | null>) {
  const markerChildrenRef = useRef<any[]>([]);
  
  // Забираем данные и экшены из Zustand-стора благоустройства Липецка
  const { incidents, selectedIncident, selectIncident } = useIncidentStore();

  useEffect(() => {
    // Если карта еще не проинициализирована хуком useYandexMap — ничего не делаем
    if (!mapReady || !mapRef.current || !window.ymaps3) return;

    const { YMapMarker } = window.ymaps3;
    const currentMap = mapRef.current;

    // Безопасно очищаем старые маркеры ТКО перед перерисовкой
    markerChildrenRef.current.forEach((marker) => {
      try { currentMap.removeChild(marker); } catch { /* ignore */ }
    });
    markerChildrenRef.current = [];

    // Расставляем новые актуальные точки нарушений на карту города
    incidents.forEach((incident) => {
      const isSelected = selectedIncident?.id === incident.id;

      // Генерируем HTML-ноду через фабрику утилит
      const markerElement = createMarkerElement(incident.status, isSelected, () => {
        selectIncident(incident.id); // Клик открывает Единое Окно
      });

      const marker = new YMapMarker({
        coordinates: [...incident.location.coordinates],
        draggable: false
      }, markerElement);

      currentMap.addChild(marker);
      markerChildrenRef.current.push(marker);
    });

  }, [mapReady, incidents, selectedIncident, selectIncident, mapRef]);
}

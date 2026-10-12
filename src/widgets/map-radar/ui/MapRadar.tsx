import React, { useRef, } from 'react';
import { useYandexMap } from '../lib/useYandexMap';
import { useIncidentMarkers } from '../lib/useIncidentMarkers';
import { STATUS_META, STATUS_ORDER } from '@/entities/incident/lib/presentation';

declare global {
  interface Window {
    ymaps3?: any;
  }
}

export const MapRadar: React.FC = () => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
   // 1. Инициализируем карту
  const { mapReady, error, mapRef } = useYandexMap(mapContainerRef);

  // 2. Одной строчкой делегируем управление маркерами новому хуку
  useIncidentMarkers(mapReady, mapRef);

  return (
    <section className="flex shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border px-5 py-3">
        <h2 className="text-[16px] font-semibold text-foreground">Карта нарушений</h2>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
          {STATUS_ORDER.map((status) => (
            <li key={status} className="flex items-center gap-1.5">
              <span
                className="size-2.5 rounded-full"
                style={{ backgroundColor: STATUS_META[status].dot }}
              />
              {STATUS_META[status].label}
            </li>
          ))}
        </ul>
      </div>

      <div className="relative h-[420px] w-full bg-muted">
        {/* Пустой узел только для Яндекса — React сюда children не кладёт */}
        <div ref={mapContainerRef} className="map-muted absolute inset-0" />

        {error && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-1 bg-muted px-6 text-center">
            <span className="text-[15px] font-medium text-foreground">Карта недоступна</span>
            <span className="max-w-md text-[13px] text-muted-foreground">{error}</span>
          </div>
        )}
        {!error && !mapReady && (
          <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-muted text-[14px] text-muted-foreground">
            Загрузка карты…
          </div>
        )}
      </div>
    </section>
  );
};

import React, { useRef, } from 'react';
import 'leaflet/dist/leaflet.css';
import { useLeafletMap } from '../lib/useLeafletMap';
import { useIncidentMarkers } from '../lib/useIncidentMarkers';
import { STATUS_META, STATUS_ORDER } from '@/entities/incident/lib/presentation';
import { useStandStore } from '@/shared/theme/standStore';

interface TProps {
  // chrome — карточка с заголовком и легендой (базовая тема);
  // без него — только карта, раскладка обрамляет её сама
  chrome?: boolean;
  className?: string;
}

// Сама карта с маркерами; при смене темы меняет подложку и цвета зон УК.
const MapCanvas: React.FC<{ className?: string }> = ({ className = '' }) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mode = useStandStore((s) => s.mode);
  const { mapReady, tilesMissing, mapRef } = useLeafletMap(mapContainerRef, mode);
  useIncidentMarkers(mapReady, mapRef);

  return (
    <div className={`relative overflow-hidden bg-muted ${className}`}>
      {/* Пустой узел только для Leaflet — React сюда children не кладёт. isolate держит z-index
          слоёв Leaflet (400–1000) внутри карты, иначе они лягут поверх панелей раскладки */}
      <div ref={mapContainerRef} className="map-base absolute inset-0 isolate" />

      {tilesMissing && (
        <div className="pointer-events-none absolute inset-x-0 top-1/2 z-20 flex justify-center px-6">
          <span className="rounded-md bg-card px-3 py-1.5 text-center text-[13px] text-muted-foreground ring-1 ring-border">
            Подложка карты не загрузилась: {tilesMissing}
          </span>
        </div>
      )}
    </div>
  );
};

export const MapRadar: React.FC<TProps> = ({ chrome = true, className = '' }) => {
  if (!chrome) return <MapCanvas className={className} />;

  return (
    <section className="flex shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border px-5 py-3">
        <h2 className="text-[16px] font-semibold text-foreground">Карта нарушений</h2>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
          {STATUS_ORDER.map((status) => (
            <li key={status} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-full" style={{ backgroundColor: STATUS_META[status].dot }} />
              {STATUS_META[status].label}
            </li>
          ))}
        </ul>
      </div>
      <MapCanvas className={`h-[420px] w-full ${className}`} />
    </section>
  );
};

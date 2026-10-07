import React, { useRef, } from 'react';
import { Card } from '@/components/ui/card';
import { Layers, Info } from 'lucide-react';
import { useYandexMap } from '../lib/useYandexMap';     
import { useIncidentMarkers } from '../lib/useIncidentMarkers';

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

  if (error) {
    return <div className="p-4 text-rose-600 bg-rose-50 rounded-xl">{error}</div>;
  }

  return (
    <Card className="relative flex h-150 w-full flex-col gap-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 py-0 shadow-sm">
      <div className="absolute top-4 left-4 z-10 flex items-center gap-4 rounded-lg border border-slate-200/80 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm backdrop-blur-xs">
        <div className="flex items-center gap-1.5 border-r border-slate-200 pr-3">
          <Layers className="h-3.5 w-3.5 text-slate-400" />
          <span>
            Слой: <span className="font-bold text-blue-600">Яндекс.Карты v3</span>
          </span>
        </div>
        <div className="flex gap-3 text-slate-700">
          <span className="flex items-center gap-1 font-bold">г. Липецк</span>
        </div>
      </div>

      <div className="relative min-h-0 w-full flex-1 bg-slate-50">
        {/* Пустой узел только для Яндекса — React сюда children не кладёт */}
        <div ref={mapContainerRef} className="absolute inset-0" />

        {error && (
          <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-slate-100 px-6 text-center text-sm text-rose-600">
            {error}
          </div>
        )}
        {!error && !mapReady && (
          <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-slate-100 text-sm text-slate-500">
            Загрузка карты…
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-slate-200 bg-white px-4 py-2.5 text-[11px] font-semibold text-slate-500">
        <div className="flex items-center gap-1">
          <div className="h-2.5 w-2.5 rounded-full bg-blue-500" /> Новые инциденты
        </div>
        <div className="flex items-center gap-1">
          <div className="h-2.5 w-2.5 rounded-full bg-amber-500" /> В работе у УК
        </div>
        <div className="flex items-center gap-1">
          <div className="h-2.5 w-2.5 rounded-full bg-purple-500" /> На верификации
        </div>
        <div className="flex items-center gap-1">
          <div className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Нарушение устранено
        </div>
        <div className="flex items-center gap-1">
          <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-rose-600" /> Эскалация в КНМ
        </div>
        <div className="ml-auto flex items-center gap-1 text-[10px] text-slate-400">
          <Info className="h-3 w-3" /> Кликните на маркер для открытия Единого Окна
        </div>
      </div>
    </Card>
  );
};

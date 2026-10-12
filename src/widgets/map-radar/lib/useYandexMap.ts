import { useEffect, useState, useRef} from 'react';
import type { RefObject } from 'react';
import { loadYmaps3 } from './mapUtils'; // Импортируем твой асинхронный загрузчик
import type { YMapInstance } from './ymapsTypes';
import { LIPETSK_POLYGONS } from './lipetskPolygons';
import { readThemeColors } from '@/shared/theme/themeColors';

interface UseYandexMapResult {
  mapReady: boolean;
  error: string | null;
  mapRef: RefObject<YMapInstance | null>;
}

/**
 * Кастомный хук для безопасной инициализации ядра Яндекс.Карт v3
 * Изолирует логику StrictMode-предохранителей, деструкторов и отмены асинхронных тасков
 */
export function useYandexMap(
  mapContainerRef: RefObject<HTMLDivElement | null>
): UseYandexMapResult {
  const [mapReady, setMapReady] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  
  // Храним сам инстанс карты в Ref, чтобы он не стирался и не вызывал ререндеры
  const mapRef = useRef<YMapInstance | null>(null);

  const apiKey = import.meta.env.VITE_YANDEX_MAPS_API_KEY;

  useEffect(() => {
    if (!apiKey) return;

    // Флаг отмены для защиты от Race Conditions (когда компонент размонтировался до того, как ответил сервер)
    let cancelled = false;

    async function initMap() {
      try {
        // Вызываем твою функцию-синглтон загрузки
        const ymaps3 = await loadYmaps3(apiKey);
        if (cancelled || !mapContainerRef.current) return;

        // Если карта каким-то образом уже существовала — принудительно зачищаем её
        if (mapRef.current) {
          try { mapRef.current.destroy(); } catch { /* ignore */ }
          mapRef.current = null;
        }

        const { YMap, YMapDefaultSchemeLayer, YMapDefaultFeaturesLayer, YMapFeatureDataSource, YMapLayer } = ymaps3;

        // Инициализируем нативный WebGL-холст Яндекса v3
        const map = new YMap(mapContainerRef.current, {
          location: {
            center: [39.598, 52.611], // Липецк [lng, lat]: весь город с левым берегом
            zoom: 12.6,
          },
        });

        // Подложку красит тема: CSS-фильтр .map-base canvas (styles/themes.css); маркеры — DOM, их фильтр не трогает
        map.addChild(new YMapDefaultSchemeLayer());
        map.addChild(new YMapDefaultFeaturesLayer());

        // 2. Источник данных для ведомственных полигонов (Обязательно по доке v3)
        const polygonsSource = new YMapFeatureDataSource({ id: 'polygons-source' });
        map.addChild(polygonsSource);

        // Слой, который будет физически отрисовывать наши цветные многоугольники
        const polygonsLayer = new YMapLayer({ dataSource: 'polygons-source', type: 'feature' });
        map.addChild(polygonsLayer);

        // 3. Рисуем каждый ведомственный полигон на карте Липецка
        // Цвета зон — из темы (карта пересоздаётся при смене темы)
        const theme = readThemeColors();
        const zoneColors = [theme['zone-1'], theme['zone-2']];
        LIPETSK_POLYGONS.forEach((poly, index) => {
          const zone = zoneColors[index % zoneColors.length] || poly.borderColor;
          // Создаем нативный графический объект Яндекса
          const zoneFeature = new ymaps3.YMapFeature({
            id: poly.id,
            geometry: {
              type: 'Polygon',
              coordinates: poly.coordinates
            },
            style: {
              fill: `${zone}24`, // заливка двора: цвет зоны + альфа 0x24 (≈14 %)
              stroke: [
                { color: zone, width: 1.5 } // граница зоны ответственности УК
              ]
            }
          });

          map.addChild(zoneFeature);
        });
        
        mapRef.current = map;

        if (!cancelled) {
          setMapReady(true);
          setError(null);
        }
      } catch (err) {
        console.error('Ошибка инициализации Яндекс.Карт:', err);
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Ошибка загрузки карты');
        }
      }
    }

    initMap();

    // Функция очистки при размонтировании виджета (Cleanup)
    return () => {
      cancelled = true;
      setMapReady(false);
      
      if (mapRef.current) {
        try {
          mapRef.current.destroy();
        } catch {
          // ignore
        }
        mapRef.current = null;
      }
    };
  }, [mapContainerRef, apiKey]); // Запускается строго один раз при привязке контейнера

  return { mapReady, error: apiKey ? error : 'Нет ключа VITE_YANDEX_MAPS_API_KEY в .env', mapRef };
}

import { useEffect, useState, useRef} from 'react';
import type { RefObject } from 'react';
import { loadYmaps3 } from './mapUtils'; // Импортируем твой асинхронный загрузчик
import { LIPETSK_POLYGONS } from './lipetskPolygons';

interface UseYandexMapResult {
  mapReady: boolean;
  error: string | null;
  mapRef: RefObject<any | null>;
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
  const mapRef = useRef<any | null>(null);

  useEffect(() => {
    const apiKey = import.meta.env.VITE_YANDEX_MAPS_API_KEY;
    if (!apiKey) {
      setError('Нет ключа VITE_YANDEX_MAPS_API_KEY в .env');
      return;
    }

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
            center: [39.5532, 52.6145], // Липецк [lng, lat]
            zoom: 13,
          },
        });

        // Подложку приглушает CSS (.map-muted в index.css): маркеры — DOM, их фильтр не трогает
        map.addChild(new YMapDefaultSchemeLayer());
        map.addChild(new YMapDefaultFeaturesLayer());

        // 2. Источник данных для ведомственных полигонов (Обязательно по доке v3)
        const polygonsSource = new YMapFeatureDataSource({ id: 'polygons-source' });
        map.addChild(polygonsSource);

        // Слой, который будет физически отрисовывать наши цветные многоугольники
        const polygonsLayer = new YMapLayer({ dataSource: 'polygons-source', type: 'feature' });
        map.addChild(polygonsLayer);

        // 3. Рисуем каждый ведомственный полигон на карте Липецка
        LIPETSK_POLYGONS.forEach((poly) => {
          // Создаем нативный графический объект Яндекса
          const zoneFeature = new ymaps3.YMapFeature({
            id: poly.id,
            geometry: {
              type: 'Polygon',
              coordinates: poly.coordinates
            },
            style: {
              fill: poly.color,         // Цвет заливки двора
              stroke: [
                { color: poly.borderColor, width: 2 } // Цвет и толщина границы забора
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
  }, [mapContainerRef]); // Запускается строго один раз при привязке контейнера

  return { mapReady, error, mapRef };
}

// Яндекс Карты v3 грузятся скриптом с api-maps.yandex.ru, пакета типов в проекте нет.
// Описано ровно то, чем пользуется виджет, — без any.

export type LngLat = [number, number];

export interface YMapInstance {
  zoom?: number;
  addChild(child: object): void;
  removeChild(child: object): void;
  update(props: { location: { center: LngLat; zoom?: number; duration?: number } }): void;
  destroy(): void;
}

type Entity<P = object> = new (props: P) => object;

export interface Ymaps3 {
  ready: Promise<void>;
  YMap: new (container: HTMLElement, props: { location: { center: LngLat; zoom: number } }) => YMapInstance;
  YMapDefaultSchemeLayer: new (props?: object) => object;
  YMapDefaultFeaturesLayer: new (props?: object) => object;
  YMapFeatureDataSource: Entity<{ id: string }>;
  YMapLayer: Entity<{ dataSource: string; type: string }>;
  YMapFeature: Entity<{
    id: string;
    geometry: { type: 'Polygon'; coordinates: number[][][] };
    style: { fill: string; stroke: { color: string; width: number }[] };
  }>;
  YMapMarker: new (props: { coordinates: LngLat; zIndex?: number; draggable?: boolean }, element: HTMLElement) => object;
}

declare global {
  interface Window {
    ymaps3?: Ymaps3;
  }
}

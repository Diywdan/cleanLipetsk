import { STATUS_META } from "@/entities/incident/lib/presentation";
import type { IncidentStatus } from "@/entities/incident/types";

let ymapsLoadPromise: Promise<any> | null = null;

export function loadYmaps3(apiKey: string): Promise<any> {
  if (window.ymaps3) {
    return window.ymaps3.ready.then(() => window.ymaps3);
  }

  if (ymapsLoadPromise) return ymapsLoadPromise;

  ymapsLoadPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      "script[data-ymaps3]",
    );

    const waitUntilReady = async () => {
      const started = Date.now();
      while (!window.ymaps3) {
        if (Date.now() - started > 15000) {
          throw new Error("Таймаут загрузки Яндекс.Карт");
        }
        await new Promise((r) => setTimeout(r, 50));
      }
      await window.ymaps3.ready;
      return window.ymaps3;
    };

    if (existing) {
      waitUntilReady().then(resolve).catch(reject);
      return;
    }

    const script = document.createElement("script");
    script.src = `https://api-maps.yandex.ru/v3/?apikey=${apiKey}&lang=ru_RU`;
    script.async = true;
    script.dataset.ymaps3 = "true";
    script.onload = () => {
      waitUntilReady().then(resolve).catch(reject);
    };
    script.onerror = () => {
      ymapsLoadPromise = null;
      reject(
        new Error(
          "Яндекс вернул отказ (часто 403). В кабинете ключа укажите HTTP Referer: localhost",
        ),
      );
    };
    document.head.appendChild(script);
  });

  return ymapsLoadPromise;
}

export function createMarkerElement(
  status: IncidentStatus,
  isSelected: boolean,
  onClick: () => void,
): HTMLDivElement {
  const el = document.createElement("div");
  const color = STATUS_META[status]?.dot ?? "#5C6B7A";
  const size = isSelected ? 26 : 18;

  // Точка цвета статуса с белой обводкой; выбранная — крупнее и с синим кольцом
  el.style.cssText = [
    `width:${size}px`,
    `height:${size}px`,
    "border-radius:9999px",
    `background:${color}`,
    "border:3px solid #fff",
    isSelected
      ? "box-shadow:0 0 0 3px #0D4CD3, 0 2px 6px rgba(11,31,51,.35)"
      : "box-shadow:0 1px 4px rgba(11,31,51,.35)",
    "transform:translate(-50%,-50%)",
    "cursor:pointer",
    `position:relative;z-index:${isSelected ? 50 : 10}`,
    "transition:width .15s,height .15s",
  ].join(";");
  el.title = STATUS_META[status]?.label ?? "";

  el.onclick = (e) => {
    e.stopPropagation();
    onClick();
  };

  return el;
}

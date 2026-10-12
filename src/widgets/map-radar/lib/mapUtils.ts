import { STATUS_META } from "@/entities/incident/lib/presentation";
import type { IncidentStatus } from "@/entities/incident/types";
import type { ThemeId } from "@/shared/theme/standStore";

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

// Маркер обращения. Вид зависит от темы:
//  dispatch — светящаяся точка, у новых и КНМ — пульс;
//  dossier  — чернильная точка с бумажной обводкой, как отметка на плане;
//  pro      — маленькая точка с тонким кольцом;
//  gos      — точка с белой обводкой.
export function createMarkerElement(
  status: IncidentStatus,
  isSelected: boolean,
  onClick: () => void,
  theme: ThemeId = "gos",
): HTMLDivElement {
  const el = document.createElement("div");
  const color = STATUS_META[status]?.dot ?? "#5C6B7A";
  const base = { gos: 18, dispatch: 14, dossier: 14, pro: 12 }[theme];
  const size = isSelected ? base + 8 : base;

  const ring: Record<ThemeId, string> = {
    gos: isSelected
      ? "border:3px solid #fff;box-shadow:0 0 0 3px var(--primary), 0 2px 6px rgba(11,31,51,.35)"
      : "border:3px solid #fff;box-shadow:0 1px 4px rgba(11,31,51,.35)",
    dispatch: isSelected
      ? `border:2px solid #fff;box-shadow:0 0 0 4px color-mix(in srgb, ${color} 35%, transparent), 0 0 22px 4px ${color}`
      : `border:1.5px solid color-mix(in srgb, ${color} 40%, #fff);box-shadow:0 0 14px 2px color-mix(in srgb, ${color} 70%, transparent)`,
    dossier: isSelected
      ? "border:2.5px solid #FBF8F1;box-shadow:0 0 0 2px var(--foreground), 0 3px 8px rgba(60,45,20,.35)"
      : "border:2px solid #FBF8F1;box-shadow:0 1px 3px rgba(60,45,20,.4)",
    pro: isSelected
      ? "border:2px solid var(--background);box-shadow:0 0 0 2px var(--primary), 0 4px 12px rgba(0,0,0,.35)"
      : "border:2px solid var(--background);box-shadow:0 0 0 1px var(--border)",
  };

  el.style.cssText = [
    `width:${size}px`,
    `height:${size}px`,
    "border-radius:9999px",
    `background:${color}`,
    `color:${color}`,
    ring[theme],
    "transform:translate(-50%,-50%)",
    "cursor:pointer",
    `position:relative;z-index:${isSelected ? 50 : 10}`,
    "transition:width .15s,height .15s,box-shadow .15s",
  ].join(";");
  if (theme === "dispatch" && (status === "NEW" || status === "KNM_ESCALATION")) {
    el.classList.add("marker-pulse");
  }
  el.title = STATUS_META[status]?.label ?? "";

  el.onclick = (e) => {
    e.stopPropagation();
    onClick();
  };

  return el;
}

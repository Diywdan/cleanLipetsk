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

export function statusColor(status: string): string {
  const colors: Record<string, string> = {
    NEW: "bg-blue-500 border-blue-200",
    IN_PROGRESS: "bg-amber-500 border-amber-200",
    VERIFICATION: "bg-purple-500 border-purple-200",
    CLOSED: "bg-emerald-500 border-emerald-200",
  };
  return colors[status] || "bg-rose-600 border-rose-300 animate-pulse";
}

export function createMarkerElement(
  status: string,
  isSelected: boolean,
  onClick: () => void,
): HTMLDivElement {
  const el = document.createElement("div");
 // Собираем декларативные Tailwind v4 классы
  const baseClasses = "w-6 h-6 rounded-full flex items-center justify-center border-2 border-white shadow-md cursor-pointer transition-all transform hover:scale-125 duration-200 -translate-x-1/2 -translate-y-1/2";
  const selectedClasses = isSelected ? "ring-4 ring-offset-2 ring-blue-500 scale-110 z-50" : "z-10";
  const statusColorClass = statusColor(status);

  el.className = `${baseClasses} ${selectedClasses} ${statusColorClass}`;

  const dot = document.createElement("div");
  dot.style.cssText =
    "width:6px;height:6px;border-radius:9999px;background:#fff;";
  el.appendChild(dot);

  el.onclick = (e) => {
    e.stopPropagation();
    onClick();
  };

  return el;
}

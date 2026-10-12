import React, { useState, useRef, useEffect } from 'react';
import { ArrowLeftRight } from 'lucide-react';

interface ImageCompareSliderProps {
  beforeUrl: string;
  afterUrl: string;
  className?: string;
}

// Координата указателя → проценты ширины контейнера (0–100)
function toPercent(el: HTMLElement | null, clientX: number): number | null {
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100));
}

export const ImageCompareSlider: React.FC<ImageCompareSliderProps> = ({
  beforeUrl,
  afterUrl,
  className = '',
}) => {
  // Положение шторки в процентах. По умолчанию — ровно по центру (50%)
  const [sliderPosition, setSliderPosition] = useState<number>(50);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const moveTo = (clientX: number) => {
    const p = toPercent(containerRef.current, clientX);
    if (p !== null) setSliderPosition(p);
  };

  // Глобальные слушатели мыши, чтобы ползунок не «срывался», если вести мышь быстро вне картинки
  useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: MouseEvent) => {
      const p = toPercent(containerRef.current, e.clientX);
      if (p !== null) setSliderPosition(p);
    };
    const onUp = () => setIsDragging(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [isDragging]);

  return (
    <div
      ref={containerRef}
      className={`relative select-none overflow-hidden rounded-md bg-ink w-full aspect-video ${className}`}
      onMouseDown={(e) => {
        moveTo(e.clientX);
        setIsDragging(true);
      }}
      onTouchMove={(e) => {
        if (e.touches.length > 0) moveTo(e.touches[0].clientX);
      }}
    >
      {/* ИЗОБРАЖЕНИЕ «СТАЛО» (Основа/Задний план) */}
      <img
        src={afterUrl}
        alt="Результат уборки УК"
        className="absolute inset-0 w-full h-full object-cover pointer-events-none"
      />
      <div
        className="absolute inset-0 overflow-hidden pointer-events-none z-20"
        style={{ clipPath: `inset(0 0 0 ${sliderPosition}%)` }}
      >
        <div className="absolute bottom-3 right-3 whitespace-nowrap rounded bg-[#0A6B34] px-2 py-0.5 text-[12px] text-white">
          Стало
        </div>
      </div>

      {/* ИЗОБРАЖЕНИЕ «БЫЛО»: во всю ширину, обрезается маской — картинка не сжимается вслед за шторкой */}
      <div
        className="absolute inset-0 pointer-events-none z-10"
        style={{ clipPath: `inset(0 ${100 - sliderPosition}% 0 0)` }}
      >
        <img src={beforeUrl} alt="Фиксация нарушения ИИ" className="w-full h-full object-cover" />
        <div className="absolute top-3 left-3 z-20 whitespace-nowrap rounded bg-ink/85 px-2 py-0.5 text-[12px] text-white">
          Было
        </div>
      </div>

      {/* ЛИНИЯ РАЗДЕЛА И ПОЛЗУНОК */}
      <div
        className="absolute inset-y-0 w-0.5 bg-white cursor-ew-resize z-30 shadow-lg flex items-center justify-center group"
        style={{ left: `${sliderPosition}%` }}
      >
        <div className="absolute w-8 h-8 rounded-full bg-white text-slate-700 shadow-xl border border-slate-200 flex items-center justify-center transition-transform group-hover:scale-110 active:scale-95">
          <ArrowLeftRight className="w-3.5 h-3.5 stroke-[2.5]" />
        </div>
      </div>
    </div>
  );
};

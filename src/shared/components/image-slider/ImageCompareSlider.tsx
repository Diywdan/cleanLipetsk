import React, { useState, useRef, useEffect } from 'react';
import { ArrowLeftRight } from 'lucide-react';

interface ImageCompareSliderProps {
  beforeUrl: string;
  afterUrl: string;
  className?: string;
}

export const ImageCompareSlider: React.FC<ImageCompareSliderProps> = ({
  beforeUrl,
  afterUrl,
  className = '',
}) => {
  // Положение шторки в процентах (от 0 до 100). По умолчанию — ровно по центру (50%)
  const [sliderPosition, setSliderPosition] = useState<number>(50);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Функция для расчета процента смещения ползунка относительно контейнера
  const handleMove = (clientX: number) => {
    if (!containerRef.current) return;
    
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left; // Пиксели от левого края контейнера
    
    // Переводим в проценты и жестко ограничиваем рамками от 0% до 100%
    let position = (x / rect.width) * 100;
    if (position < 0) position = 0;
    if (position > 100) position = 100;
    
    setSliderPosition(position);
  };

  // Обработчики для мыши
  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return;
    handleMove(e.clientX);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Глобальные слушатели мыши, чтобы ползунок не «срывался», если вести мышь быстро вне картинки
  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  return (
    <div
      ref={containerRef}
      className={`relative select-none overflow-hidden rounded-md bg-ink w-full aspect-video ${className}`}
      onMouseDown={() => setIsDragging(true)}
      onTouchMove={(e) => {
        if (e.touches.length > 0) handleMove(e.touches[0].clientX);
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

      {/* ИЗОБРАЖЕНИЕ «БЫЛО» (Верхний слой, обрезаемый по ширине) */}
      <div
        className="absolute inset-y-0 left-0 overflow-hidden pointer-events-none z-10"
        style={{ width: `${sliderPosition}%` }}
      >
        {/* Нам нужно жестко зафиксировать ширину внутренней картинки, чтобы она не сжималась вслед за контейнером */}
        <div className="absolute inset-y-0 left-0 w-full h-full" style={{ width: containerRef.current?.getBoundingClientRect().width || '100%' }}>
          <img
            src={beforeUrl}
            alt="Фиксация нарушения ИИ"
            className="w-full h-full object-cover pointer-events-none"
            style={{ width: containerRef.current?.getBoundingClientRect().width || '100%', height: '100%' }}
          />
        </div>
        <div className="absolute top-3 left-3 z-20 whitespace-nowrap rounded bg-ink/85 px-2 py-0.5 text-[12px] text-white">
          Было
        </div>
      </div>

      {/* ЛИНИЯ РАЗДЕЛА И ПОЛЗУНОК (ПОЛЗУНОК) */}
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

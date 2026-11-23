import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { Minus, Plus, X } from 'lucide-react';

const MAX_ZOOM = 3;
const STEP = 0.5;

export function PhotoViewer({ url, title, onClose }: { url: string; title: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const center = useRef<{ x: number; y: number } | null>(null);
  const titleId = useId();
  const [zoom, setZoom] = useState(1);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
  }, []);

  useLayoutEffect(() => {
    const frame = viewport.current;
    const point = center.current;
    center.current = null;
    if (frame && point) {
      frame.scrollLeft = point.x * frame.scrollWidth - frame.clientWidth / 2;
      frame.scrollTop = point.y * frame.scrollHeight - frame.clientHeight / 2;
    }
  }, [zoom]);

  function changeZoom(value: number) {
    const next = Math.min(MAX_ZOOM, Math.max(1, value));
    const frame = viewport.current;
    if (next === zoom) return;
    if (frame && frame.scrollWidth && frame.scrollHeight) {
      center.current = {
        x: (frame.scrollLeft + frame.clientWidth / 2) / frame.scrollWidth,
        y: (frame.scrollTop + frame.clientHeight / 2) / frame.scrollHeight,
      };
    }
    setZoom(next);
  }

  const control = 'grid size-10 cursor-pointer place-items-center rounded-md hover:bg-white/15 disabled:cursor-default disabled:opacity-40';
  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="m-auto h-[90dvh] max-h-none w-[96vw] max-w-6xl overflow-hidden rounded-lg bg-neutral-950 p-0 text-white backdrop:bg-black/75"
    >
      <div className="flex h-full flex-col">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/20 px-3 py-2">
          <h2 id={titleId} className="m-0 text-sm font-semibold">{title}</h2>
          <div className="flex items-center gap-1">
            <button type="button" className={control} aria-label="Уменьшить" disabled={failed || zoom <= 1} onClick={() => changeZoom(zoom - STEP)}>
              <Minus className="size-4" />
            </button>
            <button type="button" className="cursor-pointer px-2 text-sm tabular-nums" aria-label="Сбросить масштаб" onClick={() => changeZoom(1)}>
              {Math.round(zoom * 100)}%
            </button>
            <button type="button" className={control} aria-label="Увеличить" disabled={failed || zoom >= MAX_ZOOM} onClick={() => changeZoom(zoom + STEP)}>
              <Plus className="size-4" />
            </button>
            <button type="button" className={control} aria-label="Закрыть фото" onClick={onClose}>
              <X className="size-5" />
            </button>
          </div>
        </header>
        <div ref={viewport} className="min-h-0 flex-1 overflow-auto">
          {failed ? (
            <p role="alert" className="m-0 grid h-full place-items-center text-sm text-white/75">Фото не загрузилось</p>
          ) : (
            <div style={{ width: `${zoom * 100}%`, height: `${zoom * 100}%` }}>
              <img src={url} alt={title} onError={() => setFailed(true)} className="block h-full w-full max-w-none object-contain" />
            </div>
          )}
        </div>
      </div>
    </dialog>
  );
}

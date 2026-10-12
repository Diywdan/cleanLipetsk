import React, { useRef, useState } from 'react';
import { Camera, ImagePlus, MapPin, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { IIncident, IPhotoReport } from '../../types';
import { compressImage } from '@/shared/lib/image';
import { REPORT_RADIUS_M, currentPosition, distanceM } from '@/shared/lib/geo';
import { formatDateTime } from '../../lib/presentation';

// Фотоотчёт мастера УК: снимок с камеры телефона или из галереи, предпросмотр,
// время съёмки и расстояние до площадки. Инспектор видит то же в хронике и карточке.
export const PhotoReportForm: React.FC<{
  incident: IIncident;
  demoPhoto: string;
  onSubmit: (report: IPhotoReport) => Promise<void>;
  buttonClass: string;
  secondaryClass: string;
}> = ({ incident, demoPhoto, onSubmit, buttonClass, secondaryClass }) => {
  const input = useRef<HTMLInputElement>(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [takenAt, setTakenAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setProblem(null);
    setBusy(true);
    try {
      setPhoto(await compressImage(file));
      // Время съёмки: у снимка с камеры это время файла; точнее — из EXIF на бэкенде
      setTakenAt(new Date(file.lastModified || Date.now()).toISOString());
    } catch {
      setProblem('Не удалось открыть снимок. Попробуйте другой файл.');
    } finally {
      setBusy(false);
    }
  };

  // locate=false — условный снимок стенда: место не спрашиваем, это не съёмка на площадке
  const send = async (url: string, at: string, locate = true) => {
    setBusy(true);
    const coords = locate ? await currentPosition() : null;
    const report: IPhotoReport = {
      photoUrl: url,
      takenAt: at,
      coords: coords ?? undefined,
      distanceM: coords ? distanceM(coords, incident.location.coordinates) : undefined,
    };
    await onSubmit(report);
    setBusy(false);
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="m-0 text-[14px] text-muted-foreground">
        Устраните нарушение в границах площадки и снимите результат. При отправке телефон сообщит, где сделан снимок.
      </p>

      <input
        ref={input}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0])}
      />

      {photo ? (
        <figure className="m-0 overflow-hidden rounded-lg ring-1 ring-border">
          <img src={photo} alt="Снимок для отчёта" className="block aspect-video w-full object-cover" />
          <figcaption className="font-num flex items-center justify-between gap-2 bg-[var(--inset)] px-3 py-1.5 text-[12px] text-muted-foreground">
            <span>Снято {takenAt ? formatDateTime(takenAt) : '—'}</span>
            <button type="button" onClick={() => input.current?.click()} className="flex cursor-pointer items-center gap-1 hover:text-foreground">
              <RotateCcw className="size-3" /> Переснять
            </button>
          </figcaption>
        </figure>
      ) : (
        <Button variant="outline" onClick={() => input.current?.click()} disabled={busy} className={secondaryClass}>
          <Camera /> Сделать снимок или выбрать файл
        </Button>
      )}

      {problem && <p className="m-0 text-[13px] text-danger">{problem}</p>}

      <p className="m-0 flex items-center gap-1.5 text-[12px] text-muted-foreground">
        <MapPin className="size-3.5 shrink-0" />
        Снимок дальше {REPORT_RADIUS_M} м от площадки инспектор увидит с пометкой.
      </p>

      {photo ? (
        <Button onClick={() => send(photo, takenAt ?? new Date().toISOString())} disabled={busy} className={buttonClass}>
          {busy ? 'Отправляю…' : 'Отправить фотоотчёт'}
        </Button>
      ) : (
        // На стенде нет телефона с убранной площадкой — условный снимок «стало»
        <button
          type="button"
          onClick={() => send(demoPhoto, new Date().toISOString(), false)}
          disabled={busy}
          className="flex cursor-pointer items-center justify-center gap-1.5 text-[12.5px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          <ImagePlus className="size-3.5" /> Стенд: отправить условный снимок
        </button>
      )}
    </div>
  );
};

// Подпись под фото «стало» для инспектора: когда снято и далеко ли от площадки
export const ReportMeta: React.FC<{ incident: IIncident }> = ({ incident }) => {
  const r = incident.media.report;
  if (!r) return null;
  const far = r.distanceM != null && r.distanceM > REPORT_RADIUS_M;
  return (
    <p className={`font-num m-0 mt-2 flex flex-wrap gap-x-3 text-[12px] ${far ? 'text-danger' : 'text-muted-foreground'}`}>
      <span>Отчёт снят {formatDateTime(r.takenAt)}</span>
      <span>
        {r.distanceM == null
          ? 'место съёмки не определено'
          : far
            ? `${Math.round(r.distanceM)} м от площадки — проверьте, та ли площадка`
            : `${Math.round(r.distanceM)} м от площадки`}
      </span>
    </p>
  );
};

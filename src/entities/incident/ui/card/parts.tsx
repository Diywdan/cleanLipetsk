import React from 'react';
import type { IIncident, IHistoryEvent } from '../../types';
import { ImageCompareSlider } from '@/shared/components/image-slider/ImageCompareSlider';
import { ORGANIZATION_KIND_TITLE, RESPONSIBLE_ROLE_TITLE } from '../../lib/responsibles';
import { SOURCE_TITLE, formatDateTime, typoQuotes } from '../../lib/presentation';
import { slaShare } from './cardModel';
import { Bot, Building2, Settings, User } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Части карточки обращения; оболочка DispatchCard собирает из них свою композицию.
// ─────────────────────────────────────────────────────────────────────────────

/* ── Фотофиксация ───────────────────────────────────────────────────────── */

// Уголки видоискателя — фирменная деталь «Диспетчерской»
const HudCorners: React.FC = () => (
  <>
    {['left-2 top-2 border-l-2 border-t-2', 'right-2 top-2 border-r-2 border-t-2', 'bottom-2 left-2 border-b-2 border-l-2', 'bottom-2 right-2 border-b-2 border-r-2'].map(
      (pos) => (
        <span key={pos} className={`pointer-events-none absolute z-30 size-4 border-primary/80 ${pos}`} />
      ),
    )}
  </>
);

export const PhotoEvidence: React.FC<{
  incident: IIncident;
  showAi: boolean;
}> = ({ incident, showAi }) => {
  const { media, location, source, timeline } = incident;
  const boxColor = 'var(--st-knm)';
  const frame = 'rounded-lg bg-black ring-1 ring-border';

  const picture = media.photoAfterUrl ? (
    <ImageCompareSlider beforeUrl={media.photoBeforeUrl} afterUrl={media.photoAfterUrl} />
  ) : (
    <div className="relative aspect-video overflow-hidden">
      <img
        src={media.photoBeforeUrl}
        alt={`Фото нарушения: ${location.address}`}
        className="pointer-events-none h-full w-full object-cover"
      />
      {showAi &&
        media.boundingBoxes.map((box) => (
          <div
            key={box.id}
            className="absolute border-2"
            style={{
              left: `${box.x}%`,
              top: `${box.y}%`,
              width: `${box.width}%`,
              height: `${box.height}%`,
              borderColor: boxColor,
              boxShadow: `0 0 16px -2px ${boxColor}`,
            }}
          >
            <span
              className="font-num absolute left-[-2px] top-[-22px] whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11.5px] text-white"
              style={{ backgroundColor: boxColor }}
            >
              {box.label} · {(box.confidence * 100).toFixed(0)}%
            </span>
          </div>
        ))}
    </div>
  );

  return (
    <figure className="m-0">
      <div className={`relative overflow-hidden ${frame}`}>
        {picture}
        <HudCorners />
        <span className="font-num pointer-events-none absolute bottom-2.5 left-3 z-30 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-white/85">
          {SOURCE_TITLE[source].toUpperCase()} · {formatDateTime(timeline.createdAt)}
        </span>
      </div>
    </figure>
  );
};

/* ── Переключатель разметки ИИ ──────────────────────────────────────────── */

export const AiToggle: React.FC<{ checked: boolean; onChange: (v: boolean) => void; label?: string }> = ({
  checked,
  onChange,
  label = 'Разметка ИИ',
}) => (
  <label className="inline-flex cursor-pointer select-none items-center gap-2 text-[12.5px] text-muted-foreground">
    <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
    <span className="relative h-[18px] w-8 rounded-full bg-input transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-3.5 after:rounded-full after:bg-white after:transition-transform after:content-[''] peer-checked:bg-primary peer-checked:after:translate-x-3.5 peer-focus-visible:ring-2 peer-focus-visible:ring-ring/50" />
    {label}
  </label>
);

/* ── Площадка ───────────────────────────────────────────────────────────── */

export const KpValue: React.FC<{ incident: IIncident; mono?: boolean }> = ({ incident, mono }) => {
  const { kp } = incident;
  if (!kp) return <span className="text-warning">Не определена — обращение по дому</span>;
  return (
    <span>
      <span className={mono ? 'font-num' : undefined}>{kp.code}</span>
      {kp.registryNumber && <span className="text-muted-foreground"> · реестр {kp.registryNumber}</span>}
      {kp.score < 0.75 && <span className="block text-[12.5px] text-warning">сопоставлена неуверенно ({Math.round(kp.score * 100)} %)</span>}
    </span>
  );
};

/* ── Ответственные ──────────────────────────────────────────────────────── */

export const ResponsiblesList: React.FC<{ incident: IIncident }> = ({ incident }) => {
  const { responsibles } = incident;
  if (responsibles.length === 0) return <span className="text-muted-foreground">Не определены</span>;

  return (
    <ul className="m-0 list-none divide-y divide-border rounded-lg border border-border bg-[var(--inset)] p-0">
      {responsibles.map((r) => (
        <li key={`${r.role}-${r.organization.id}`} className="flex items-start gap-3 px-3 py-2">
          <Building2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <div className="text-[12.5px] text-muted-foreground">{RESPONSIBLE_ROLE_TITLE[r.role]}</div>
            <div className="text-[14px] font-medium text-foreground">
              {typoQuotes(r.organization.name)}
              <span className="font-normal text-muted-foreground">
                {' '}· {ORGANIZATION_KIND_TITLE[r.organization.kind]}
                {!r.confirmed && ' · не подтверждено'}
              </span>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
};

/* ── История ────────────────────────────────────────────────────────────── */

const AUTHOR: Record<IHistoryEvent['type'], { title: string; icon: React.ReactNode }> = {
  AI: { title: 'ИИ', icon: <Bot className="size-3.5" /> },
  INSPECTOR: { title: 'Инспектор', icon: <User className="size-3.5" /> },
  UK: { title: 'Исполнитель', icon: <Building2 className="size-3.5" /> },
  SYSTEM: { title: 'Система', icon: <Settings className="size-3.5" /> },
};

const shortTime = (iso: string) =>
  new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

export const HistoryList: React.FC<{ history?: IHistoryEvent[] }> = ({ history = [] }) => {
  if (history.length === 0) return <p className="text-[14px] text-muted-foreground">Действий по делу пока нет.</p>;

  return (
    <ol className="relative m-0 ml-3 list-none space-y-4 border-l border-border p-0">
      {history.map((e) => (
        <li key={e.id} className="relative pl-6">
          <span
            className="absolute -left-3 top-0 grid size-6 place-items-center rounded-full border border-border bg-popover text-primary"
            title={AUTHOR[e.type].title}
          >
            {AUTHOR[e.type].icon}
          </span>
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-[13.5px] font-medium text-foreground">{e.title}</span>
            <time className="font-num shrink-0 text-[12px] text-muted-foreground" dateTime={e.timestamp}>
              {shortTime(e.timestamp)}
            </time>
          </div>
          <p className="m-0 mt-0.5 text-[13px] text-muted-foreground">{e.description}</p>
        </li>
      ))}
    </ol>
  );
};

/* ── Срок устранения ────────────────────────────────────────────────────── */

export const SlaMeter: React.FC<{
  incident: IIncident;
  formattedTime: string;
  msLeft: number;
  isExpired: boolean;
  label: string;
}> = ({ incident, formattedTime, msLeft, isExpired, label }) => {
  const share = slaShare(incident, msLeft);
  const tone = isExpired ? 'var(--st-knm)' : share > 0.75 ? 'var(--st-work)' : 'var(--primary)';

  return (
    <div className="rounded-lg bg-[var(--inset)] px-4 py-3 ring-1 ring-border">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="eyebrow">До окончания срока</div>
          <div className="mt-0.5 text-[12.5px] text-muted-foreground">{label}</div>
        </div>
        <div
          className={`font-num text-[26px] font-semibold leading-none ${isExpired ? 'text-danger' : 'text-foreground'}`}
          style={{ textShadow: `0 0 18px ${tone}` }}
        >
          {formattedTime}
        </div>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-foreground/10" role="progressbar" aria-valuenow={Math.round(share * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Израсходовано срока">
        <div
          className="h-full rounded-full transition-[width] duration-700"
          style={{ width: `${Math.max(3, share * 100)}%`, background: tone, boxShadow: `0 0 12px ${tone}` }}
        />
      </div>
    </div>
  );
};

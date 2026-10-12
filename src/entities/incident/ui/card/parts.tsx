import React from 'react';
import type { IIncident, IHistoryEvent } from '../../types';
import type { ThemeId } from '@/shared/theme/standStore';
import type { UserRole } from '@/entities/user/types';
import { Button } from '@/components/ui/button';
import { ImageCompareSlider } from '@/shared/components/image-slider/ImageCompareSlider';
import { ORGANIZATION_KIND_TITLE, RESPONSIBLE_ROLE_TITLE } from '../../lib/responsibles';
import { SOURCE_TITLE, formatDateTime, formatDeadline, lowerFirst, typoQuotes } from '../../lib/presentation';
import { slaShare } from './cardModel';
import { isDeadlineFixed, resolveDeadlineHours } from '../../lib/sla';
import { generateKnmAct } from '../../lib/generateKnmAct';
import { Bot, Building2, Camera, CheckCircle2, FileDown, Settings, User } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Части карточки обращения. Каждая умеет выглядеть по-своему в каждой теме
// (variant); оболочки карточек в DispatchCard / DossierCard / ProCard собирают
// из них свою композицию.
// ─────────────────────────────────────────────────────────────────────────────

export type CardVariant = ThemeId;

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
  variant: CardVariant;
  showAi: boolean;
}> = ({ incident, variant, showAi }) => {
  const { media, location, source, timeline } = incident;
  const boxColor = variant === 'dispatch' ? 'var(--st-knm)' : variant === 'dossier' ? 'var(--danger)' : 'var(--st-knm)';

  const frame: Record<CardVariant, string> = {
    gos: 'rounded-md bg-ink',
    dispatch: 'rounded-lg bg-black ring-1 ring-border',
    dossier: 'bg-[#2a2723] p-1.5 shadow-[0_1px_0_rgba(0,0,0,0.04)] ring-1 ring-border',
    pro: 'rounded-md bg-black ring-1 ring-border',
  };

  const picture = media.photoAfterUrl ? (
    <ImageCompareSlider beforeUrl={media.photoBeforeUrl} afterUrl={media.photoAfterUrl} />
  ) : (
    <div className="relative aspect-video overflow-hidden">
      <img
        src={media.photoBeforeUrl}
        alt={`Фото нарушения: ${location.address}`}
        className={`pointer-events-none h-full w-full object-cover ${variant === 'dossier' ? 'grayscale-[0.35] sepia-[0.15]' : ''}`}
      />
      {showAi &&
        media.boundingBoxes.map((box) => (
          <div
            key={box.id}
            className={`absolute ${variant === 'dossier' ? 'border' : 'border-2'}`}
            style={{
              left: `${box.x}%`,
              top: `${box.y}%`,
              width: `${box.width}%`,
              height: `${box.height}%`,
              borderColor: boxColor,
              boxShadow: variant === 'dispatch' ? `0 0 16px -2px ${boxColor}` : undefined,
            }}
          >
            <span
              className={`absolute left-[-2px] top-[-22px] whitespace-nowrap px-1.5 py-0.5 text-[11.5px] text-white ${
                variant === 'dispatch' || variant === 'pro' ? 'font-num rounded-sm' : ''
              }`}
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
      <div className={`relative overflow-hidden ${frame[variant]}`}>
        {picture}
        {variant === 'dispatch' && (
          <>
            <HudCorners />
            <span className="font-num pointer-events-none absolute bottom-2.5 left-3 z-30 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-white/85">
              {SOURCE_TITLE[source].toUpperCase()} · {formatDateTime(timeline.createdAt)}
            </span>
          </>
        )}
      </div>
      {variant === 'dossier' && (
        <figcaption className="font-display mt-2 text-[13px] italic leading-snug text-muted-foreground">
          Снимок. {SOURCE_TITLE[source]}, {formatDateTime(timeline.createdAt)}.
          {media.photoAfterUrl ? ' Слева — было, справа — стало.' : media.boundingBoxes.length > 0 && ` Разметка: ${media.boundingBoxes.map((b) => lowerFirst(b.label)).join(', ')}.`}
        </figcaption>
      )}
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

export const ResponsiblesList: React.FC<{ incident: IIncident; variant: CardVariant }> = ({ incident, variant }) => {
  const { responsibles } = incident;
  if (responsibles.length === 0) return <span className="text-muted-foreground">Не определены</span>;

  if (variant === 'dossier') {
    return (
      <ol className="m-0 list-none space-y-2 p-0">
        {responsibles.map((r, i) => (
          <li key={`${r.role}-${r.organization.id}`} className="flex gap-3">
            <span className="font-display w-4 shrink-0 text-muted-foreground">{i + 1}.</span>
            <span>
              <span className="text-foreground">{typoQuotes(r.organization.name)}</span>
              <span className="text-muted-foreground"> — {lowerFirst(RESPONSIBLE_ROLE_TITLE[r.role])}</span>
              {!r.confirmed && <span className="text-warning"> (не подтверждено)</span>}
            </span>
          </li>
        ))}
      </ol>
    );
  }

  const rowCls: Record<CardVariant, string> = {
    gos: 'divide-y divide-border rounded-md border border-border',
    dispatch: 'divide-y divide-border rounded-lg border border-border bg-black/20',
    pro: 'divide-y divide-border rounded-md border border-border',
    dossier: '',
  };

  return (
    <ul className={`m-0 list-none p-0 ${rowCls[variant]}`}>
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

export const HistoryList: React.FC<{ history?: IHistoryEvent[]; variant: CardVariant }> = ({ history = [], variant }) => {
  if (history.length === 0) return <p className="text-[14px] text-muted-foreground">Действий по делу пока нет.</p>;

  if (variant === 'dossier') {
    // Хроника: дата на полях, текст справа
    return (
      <ol className="m-0 list-none space-y-3 p-0">
        {history.map((e) => (
          <li key={e.id} className="grid grid-cols-[88px_1fr] gap-3">
            <time className="font-display pt-px text-[13px] text-muted-foreground" dateTime={e.timestamp}>
              {shortTime(e.timestamp)}
            </time>
            <div>
              <div className="text-[14px] font-medium text-foreground">{e.title}</div>
              <p className="m-0 text-[13.5px] text-muted-foreground">{e.description}</p>
            </div>
          </li>
        ))}
      </ol>
    );
  }

  return (
    <ol className="relative m-0 ml-3 list-none space-y-4 border-l border-border p-0">
      {history.map((e) => (
        <li key={e.id} className="relative pl-6">
          <span
            className={`absolute -left-3 top-0 grid size-6 place-items-center rounded-full border border-border text-muted-foreground ${
              variant === 'dispatch' ? 'bg-[#0A1426] text-primary' : 'bg-card'
            }`}
            title={AUTHOR[e.type].title}
          >
            {AUTHOR[e.type].icon}
          </span>
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-[13.5px] font-medium text-foreground">{e.title}</span>
            <time className={`shrink-0 text-[12px] text-muted-foreground ${variant !== 'gos' ? 'font-num' : ''}`} dateTime={e.timestamp}>
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
  variant: CardVariant;
  formattedTime: string;
  msLeft: number;
  isExpired: boolean;
  label: string;
}> = ({ incident, variant, formattedTime, msLeft, isExpired, label }) => {
  const share = slaShare(incident, msLeft);
  const tone = isExpired ? 'var(--st-knm)' : share > 0.75 ? 'var(--st-work)' : 'var(--primary)';

  if (variant === 'dossier') {
    return (
      <div className="border-y border-foreground/70 py-3">
        <div className="flex items-baseline justify-between gap-4">
          <span className="eyebrow">Срок устранения</span>
          <span className={`font-display text-[26px] leading-none ${isExpired ? 'text-danger' : 'text-foreground'}`}>
            {formattedTime}
          </span>
        </div>
        <div className="mt-2 text-[13px] text-muted-foreground">
          {label}. Истекает {formatDateTime(incident.timeline.deadlineAt!)}.
        </div>
      </div>
    );
  }

  return (
    <div className={`rounded-lg px-4 py-3 ${variant === 'dispatch' ? 'bg-black/25 ring-1 ring-border' : 'bg-muted'}`}>
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className={variant === 'dispatch' ? 'eyebrow' : 'text-[12.5px] text-muted-foreground'}>До окончания срока</div>
          <div className="mt-0.5 text-[12.5px] text-muted-foreground">{label}</div>
        </div>
        <div
          className={`font-num text-[26px] font-semibold leading-none ${isExpired ? 'text-danger' : 'text-foreground'}`}
          style={variant === 'dispatch' ? { textShadow: `0 0 18px ${tone}` } : undefined}
        >
          {formattedTime}
        </div>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-foreground/10" role="progressbar" aria-valuenow={Math.round(share * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Израсходовано срока">
        <div
          className="h-full rounded-full transition-[width] duration-700"
          style={{ width: `${Math.max(3, share * 100)}%`, background: tone, boxShadow: variant === 'dispatch' ? `0 0 12px ${tone}` : undefined }}
        />
      </div>
    </div>
  );
};

/* ── Действия по роли и статусу ─────────────────────────────────────────── */

export interface CardActionHandlers {
  confirmIncident: () => void;
  rejectIncident: (id: string) => void;
  approveIncident: (id: string) => void;
  submitPhotoReport: (id: string, url: string) => void;
  selectedDeadline: 24 | 48 | 72;
  setSelectedDeadline: (h: 24 | 48 | 72) => void;
  afterPhoto: string;
}

export const CardActions: React.FC<{
  incident: IIncident;
  role: UserRole;
  variant: CardVariant;
  h: CardActionHandlers;
}> = ({ incident, role, variant, h }) => {
  const { id, status, source } = incident;
  // Длинные подписи («Сформировать акт и предписание (PDF)») переносятся, а не обрезаются
  const btn = variant === 'pro' ? 'h-auto min-h-8 whitespace-normal py-1.5 text-[13px]' : 'h-auto min-h-10 whitespace-normal py-2 text-[14px]';
  const primary =
    variant === 'dispatch'
      ? `${btn} font-semibold hover:bg-primary/90 shadow-[0_0_28px_-6px_var(--primary)]`
      : variant === 'dossier'
        ? `${btn} font-medium tracking-wide hover:bg-primary/90`
        : `${btn} hover:bg-primary/90`;
  const secondary = `${btn} ${variant === 'dispatch' ? 'bg-transparent hover:bg-white/5' : ''}`;
  const note = (tone: 'ok' | 'bad', text: string) => (
    <p
      className={`m-0 flex items-start gap-2 rounded-md px-3 py-2.5 text-[14px] ${
        tone === 'ok' ? 'text-success' : 'text-danger'
      } ${variant === 'dossier' ? 'border border-current bg-transparent' : ''}`}
      style={variant === 'dossier' ? undefined : { background: tone === 'ok' ? 'var(--st-done-bg)' : 'var(--st-knm-bg)' }}
    >
      {tone === 'ok' && <CheckCircle2 className="mt-0.5 size-4 shrink-0" />}
      {text}
    </p>
  );

  if (role === 'INSPECTOR' && status === 'NEW') {
    return (
      <div className="flex flex-col gap-3">
        {isDeadlineFixed(source) ? (
          <p className="m-0 text-[14px] text-foreground">
            Срок устранения установлен регламентом:{' '}
            <b className="font-semibold">{formatDeadline(resolveDeadlineHours(source, 48))}</b>
          </p>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className={variant === 'dispatch' || variant === 'dossier' ? 'eyebrow' : 'text-[14px] text-foreground'}>
              Срок устранения
            </span>
            <div className="flex rounded-md border border-input p-0.5" role="radiogroup" aria-label="Срок устранения">
              {([24, 48, 72] as const).map((hours) => (
                <button
                  key={hours}
                  type="button"
                  role="radio"
                  aria-checked={h.selectedDeadline === hours}
                  onClick={() => h.setSelectedDeadline(hours)}
                  className={`cursor-pointer rounded px-3 py-1 text-[13.5px] transition-colors ${
                    variant !== 'gos' ? 'font-num' : ''
                  } ${h.selectedDeadline === hours ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-muted'}`}
                >
                  {hours} ч
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1.3fr]">
          <Button variant="outline" onClick={() => h.rejectIncident(id)} className={`${secondary} text-danger`}>
            Ложное срабатывание
          </Button>
          <Button onClick={() => h.confirmIncident()} className={primary}>
            Подтвердить и направить в УК
          </Button>
        </div>
      </div>
    );
  }

  if (role === 'UK' && status === 'IN_PROGRESS') {
    return (
      <div className="flex flex-col gap-3">
        <p className="m-0 text-[14px] text-muted-foreground">
          Устраните нарушение в границах площадки и приложите фото результата.
        </p>
        <Button onClick={() => h.submitPhotoReport(id, h.afterPhoto)} className={primary}>
          <Camera /> Отправить фотоотчёт
        </Button>
      </div>
    );
  }

  if (role === 'INSPECTOR' && status === 'VERIFICATION') {
    return (
      <div className="flex flex-col gap-3">
        <p className="m-0 text-[14px] text-muted-foreground">Сравните снимки «было» и «стало»: передвиньте шторку на фото.</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Button variant="outline" onClick={() => h.rejectIncident(id)} className={secondary}>
            Вернуть на доработку
          </Button>
          <Button onClick={() => h.approveIncident(id)} className={primary}>
            Принять и закрыть
          </Button>
        </div>
      </div>
    );
  }

  if (status === 'CLOSED') return note('ok', 'Нарушение устранено. Дело закрыто.');

  if (status === 'KNM_ESCALATION') {
    return (
      <div className="flex flex-col gap-3">
        {note('bad', 'Срок устранения истёк. Материалы готовятся к передаче на контрольно-надзорное мероприятие.')}
        {role === 'INSPECTOR' && (
          <Button onClick={() => generateKnmAct(incident)} className={primary}>
            <FileDown /> Сформировать акт и предписание (PDF)
          </Button>
        )}
      </div>
    );
  }

  if (role === 'UK' && status === 'NEW') {
    return <p className="m-0 text-[14px] text-muted-foreground">Обращение на проверке у инспектора ДРТ.</p>;
  }
  if (role === 'INSPECTOR' && status === 'IN_PROGRESS') {
    return <p className="m-0 text-[14px] text-muted-foreground">Ждём фотоотчёт исполнителя.</p>;
  }
  if (role === 'UK' && status === 'VERIFICATION') {
    return <p className="m-0 text-[14px] text-muted-foreground">Фотоотчёт отправлен, инспектор проверяет.</p>;
  }
  if (role === 'ADMIN') {
    return <p className="m-0 text-[14px] text-muted-foreground">Режим просмотра: решения по делу принимают инспектор и исполнитель.</p>;
  }
  return null;
};

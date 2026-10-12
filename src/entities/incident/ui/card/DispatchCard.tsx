import React from 'react';
import { X, MapPin } from 'lucide-react';
import type { UserRole } from '@/entities/user/types';
import { STATUS_META } from '../../lib/presentation';
import { StatusTag } from '../StatusTag';
import { useCardModel, sourceLine } from './cardModel';
import { AiToggle, CardActions, HistoryList, KpValue, PhotoEvidence, ResponsiblesList, SlaMeter } from './parts';

// «Диспетчерская»: карточка — стеклянная панель над картой.
// Вверху светится полоса цвета стадии, цифры моноширинные, фото в видоискателе.
const Fact: React.FC<{ label: string; children: React.ReactNode; alarm?: boolean }> = ({ label, children, alarm }) => (
  <div className="rounded-lg border border-border bg-[var(--inset)] px-3 py-2.5">
    <div className="eyebrow">{label}</div>
    <div className={`mt-1 text-[13.5px] ${alarm ? 'text-danger' : 'text-foreground'}`}>{children}</div>
  </div>
);

const Section: React.FC<{ title: string; aside?: React.ReactNode; children: React.ReactNode }> = ({ title, aside, children }) => (
  <section>
    <div className="mb-2.5 flex items-center justify-between gap-3">
      <h3 className="eyebrow m-0">{title}</h3>
      {aside}
    </div>
    {children}
  </section>
);

export const DispatchCard: React.FC<{ role: UserRole }> = ({ role }) => {
  const m = useCardModel();
  if (!m.incident) return null;
  const inc = m.incident;
  const tone = STATUS_META[inc.status].dot;
  const repeats = m.primary?.recidivismCount ?? 0;

  return (
    <article className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* Световая полоса стадии */}
      <div className="h-[3px] shrink-0" style={{ background: `linear-gradient(90deg, transparent, ${tone}, transparent)`, boxShadow: `0 0 18px ${tone}` }} />

      <header className="shrink-0 px-5 pb-4 pt-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="font-num text-[13px] text-muted-foreground">№</span>
            <span className="font-num text-[22px] font-semibold leading-none text-foreground">{inc.id}</span>
            <StatusTag status={inc.status} />
          </div>
          <button
            type="button"
            onClick={m.close}
            className="grid size-8 cursor-pointer place-items-center rounded-md text-muted-foreground transition-colors hover:bg-[var(--hover)] hover:text-foreground"
            aria-label="Закрыть карточку"
          >
            <X className="size-4" />
          </button>
        </div>
        <h2 className="mt-3 flex items-start gap-2 text-[19px] font-semibold leading-snug text-foreground">
          <MapPin className="mt-1 size-4 shrink-0 text-primary" />
          {inc.location.address}
        </h2>
        <p className="font-num m-0 mt-1 text-[12px] text-muted-foreground">{sourceLine(inc)}</p>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 pb-5">
        {m.sla.active && (
          <SlaMeter incident={inc} variant="dispatch" formattedTime={m.sla.formattedTime} msLeft={m.sla.msLeft} isExpired={m.sla.isExpired} label={m.sla.label} />
        )}

        <Section title="Фотофиксация" aside={!inc.media.photoAfterUrl && <AiToggle checked={m.showAi} onChange={m.setShowAi} />}>
          <PhotoEvidence incident={inc} variant="dispatch" showAi={m.showAi} />
        </Section>

        <div className="grid grid-cols-2 gap-2">
          <Fact label="Площадка"><KpValue incident={inc} mono /></Fact>
          <Fact label="Кадастр"><span className="font-num">{inc.location.cadastralNumber || '—'}</span></Fact>
          {role === 'INSPECTOR' && (
            <>
              <Fact label="Контакт исполнителя"><span className="font-num">{m.primary?.organization.phone || 'нет данных'}</span></Fact>
              <Fact label="Нарушений за месяц" alarm={repeats > 2}>
                <span className="font-num text-[18px] font-semibold">{repeats}</span>
                {repeats > 2 && <span className="ml-1.5 text-[12px]">повторное</span>}
              </Fact>
            </>
          )}
        </div>

        <Section title="Ответственные">
          <ResponsiblesList incident={inc} variant="dispatch" />
        </Section>

        <Section title="Хроника">
          <HistoryList history={inc.timeline.history} variant="dispatch" />
        </Section>
      </div>

      <footer className="shrink-0 border-t border-border bg-[var(--inset)] px-5 py-4">
        <CardActions incident={inc} role={role} variant="dispatch" h={m.handlers} />
      </footer>
    </article>
  );
};

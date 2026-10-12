import React from 'react';
import { X } from 'lucide-react';
import type { UserRole } from '@/entities/user/types';
import { useAuthStore } from '@/entities/user/model/authStore';
import { STATUS_META, formatDateTime, typoQuotes } from '../../lib/presentation';
import { useCardModel, sourceLine } from './cardModel';
import { AiToggle, CardActions, HistoryList, KpValue, PhotoEvidence, ResponsiblesList, SlaMeter } from './parts';

// «Досье»: карточка — лист служебной записки. Стадия — штамп в углу,
// поля — с отточием, в конце строка подписи инспектора.

// Штамп стадии: двойная рамка, капитель, лёгкий поворот — как резиновая печать
const Stamp: React.FC<{ status: keyof typeof STATUS_META }> = ({ status }) => (
  <div
    className="pointer-events-none select-none px-2.5 py-1 text-center text-[11.5px] font-bold uppercase leading-tight tracking-[0.16em] opacity-90"
    style={{
      color: STATUS_META[status].text,
      border: '3px double currentColor',
      transform: 'rotate(-5deg)',
      fontFamily: 'var(--font-ui)',
    }}
  >
    {STATUS_META[status].label}
  </div>
);

// Строка «подпись ........ значение»
const Leader: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-baseline gap-2 py-1 text-[14px]">
    <span className="shrink-0 text-muted-foreground">{label}</span>
    <span className="min-w-6 flex-1 translate-y-[-3px] border-b border-dotted border-foreground/35" />
    <span className="max-w-[62%] text-right text-foreground">{children}</span>
  </div>
);

const Section: React.FC<{ n: string; title: string; aside?: React.ReactNode; children: React.ReactNode }> = ({ n, title, aside, children }) => (
  <section>
    <div className="mb-3 flex items-baseline justify-between gap-3 border-b border-border pb-1.5">
      <h3 className="font-display m-0 text-[16px] font-bold text-foreground">
        <span className="mr-2 font-normal text-muted-foreground">{n}</span>
        {title}
      </h3>
      {aside}
    </div>
    {children}
  </section>
);

export const DossierCard: React.FC<{ role: UserRole }> = ({ role }) => {
  const m = useCardModel();
  const user = useAuthStore((s) => s.currentUser);
  if (!m.incident) return null;
  const inc = m.incident;
  const repeats = m.primary?.recidivismCount ?? 0;

  return (
    <article className="relative flex h-full min-h-0 flex-col bg-card shadow-[var(--panel-shadow)] ring-1 ring-border">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <header className="relative px-7 pb-5 pt-6">
          <div className="flex items-baseline justify-between gap-3 border-b-2 border-double border-foreground/70 pb-2">
            <span className="eyebrow">Служебная записка</span>
            <div className="flex items-center gap-3">
              <span className="font-display text-[15px] text-foreground">№ {inc.id}</span>
              <button type="button" onClick={m.close} className="cursor-pointer text-muted-foreground hover:text-foreground" aria-label="Закрыть записку">
                <X className="size-4" />
              </button>
            </div>
          </div>
          <div className="mt-4 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="font-display m-0 text-[26px] font-bold leading-[1.15] text-foreground">{inc.location.address}</h2>
              <p className="font-display m-0 mt-1.5 text-[14px] italic text-muted-foreground">{sourceLine(inc)}</p>
            </div>
            <div className="shrink-0 pt-1">
              <Stamp status={inc.status} />
            </div>
          </div>
        </header>

        <div className="flex flex-col gap-6 px-7 pb-6">
          {m.sla.active && (
            <SlaMeter incident={inc} variant="dossier" formattedTime={m.sla.formattedTime} msLeft={m.sla.msLeft} isExpired={m.sla.isExpired} label={m.sla.label} />
          )}

          <Section n="I." title="Фотофиксация" aside={!inc.media.photoAfterUrl && <AiToggle checked={m.showAi} onChange={m.setShowAi} label="Разметка" />}>
            <PhotoEvidence incident={inc} variant="dossier" showAi={m.showAi} />
          </Section>

          <Section n="II." title="Объект">
            <Leader label="Контейнерная площадка"><KpValue incident={inc} /></Leader>
            <Leader label="Кадастровый номер">{inc.location.cadastralNumber || 'не определён'}</Leader>
            <Leader label="Управа">№ {inc.location.upravaId}</Leader>
            {role === 'INSPECTOR' && (
              <>
                <Leader label="Телефон исполнителя">{m.primary?.organization.phone || 'нет данных'}</Leader>
                <Leader label="Нарушений за месяц">
                  <span className={repeats > 2 ? 'font-bold text-danger' : undefined}>{repeats}</span>
                </Leader>
              </>
            )}
          </Section>

          <Section n="III." title="Ответственность">
            <ResponsiblesList incident={inc} variant="dossier" />
          </Section>

          <Section n="IV." title="Ход дела">
            <HistoryList history={inc.timeline.history} variant="dossier" />
            {inc.timeline.deadlineAt && (
              <p className="font-display m-0 mt-3 text-[13.5px] italic text-muted-foreground">
                Срок устранения — до {formatDateTime(inc.timeline.deadlineAt)}.
              </p>
            )}
          </Section>

          {role === 'INSPECTOR' && user && (
            <div className="mt-2 grid grid-cols-[auto_1fr_auto] items-end gap-3 text-[13.5px] text-muted-foreground">
              <span>Инспектор ДРТ</span>
              <span className="border-b border-foreground/50" />
              <span className="font-display italic text-foreground">{typoQuotes(user.name)}</span>
            </div>
          )}
        </div>
      </div>

      <footer className="shrink-0 border-t border-border bg-muted px-7 py-4">
        <CardActions incident={inc} role={role} variant="dossier" h={m.handlers} />
      </footer>
    </article>
  );
};

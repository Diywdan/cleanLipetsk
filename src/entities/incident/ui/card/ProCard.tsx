import React from 'react';
import { X, ChevronRight } from 'lucide-react';
import type { UserRole } from '@/entities/user/types';
import { STATUS_META, SOURCE_TITLE, formatDateTime, typoQuotes } from '../../lib/presentation';
import { StatusIcon } from '../StatusIcon';
import { useCardModel } from './cardModel';
import { AiToggle, CardActions, HistoryList, KpValue, PhotoEvidence, ResponsiblesList } from './parts';
import { useNow, timeLeft } from '@/shared/lib/time';

// «Профинструмент»: карточка как задача в трекере — свойства слева подписью,
// справа значением, ниже фото и активность. Плотно и без украшений.
const Prop: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="grid min-h-8 grid-cols-[116px_1fr] items-center gap-3 text-[13px]">
    <span className="text-muted-foreground">{label}</span>
    <span className="min-w-0 truncate text-foreground">{children}</span>
  </div>
);

const Block: React.FC<{ title: string; aside?: React.ReactNode; children: React.ReactNode }> = ({ title, aside, children }) => (
  <section className="border-t border-border px-5 py-4">
    <div className="mb-3 flex items-center justify-between">
      <h3 className="m-0 text-[12.5px] font-medium text-muted-foreground">{title}</h3>
      {aside}
    </div>
    {children}
  </section>
);

export const ProCard: React.FC<{ role: UserRole }> = ({ role }) => {
  const m = useCardModel();
  const now = useNow(30_000);
  if (!m.incident) return null;
  const inc = m.incident;
  const repeats = m.primary?.recidivismCount ?? 0;
  const left = inc.timeline.deadlineAt && inc.status === 'IN_PROGRESS' ? timeLeft(inc.timeline.deadlineAt, now) : null;

  return (
    <article className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border px-4 text-[12.5px] text-muted-foreground">
        <span className="flex items-center gap-1">
          Обращения <ChevronRight className="size-3.5" /> <span className="font-num text-foreground">{inc.id}</span>
        </span>
        <button type="button" onClick={m.close} className="grid size-7 cursor-pointer place-items-center rounded hover:bg-accent hover:text-foreground" aria-label="Закрыть (Esc)" title="Закрыть · Esc">
          <X className="size-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="px-5 pb-4 pt-5">
          <h2 className="m-0 text-[19px] font-semibold leading-snug tracking-[-0.01em] text-foreground">{inc.location.address}</h2>
          <p className="m-0 mt-1 text-[12.5px] text-muted-foreground">
            {SOURCE_TITLE[inc.source]} · {formatDateTime(inc.timeline.createdAt)}
          </p>
        </div>

        <div className="space-y-0.5 px-5 pb-4">
          <Prop label="Стадия">
            <span className="inline-flex items-center gap-2">
              <StatusIcon status={inc.status} /> {STATUS_META[inc.status].label}
            </span>
          </Prop>
          {left && (
            <Prop label="Срок">
              <span className={left.overdue ? 'text-danger' : left.ms < 6 * 3_600_000 ? 'text-warning' : undefined}>
                {left.overdue ? left.text : `осталось ${left.text}`}
              </span>
            </Prop>
          )}
          <Prop label="Исполнитель">{typoQuotes(m.primary?.organization.name ?? '—')}</Prop>
          <Prop label="Площадка"><KpValue incident={inc} mono /></Prop>
          <Prop label="Управа">№ {inc.location.upravaId}</Prop>
          <Prop label="Кадастр"><span className="font-num text-[12.5px]">{inc.location.cadastralNumber || '—'}</span></Prop>
          {role === 'INSPECTOR' && (
            <>
              <Prop label="Телефон"><span className="font-num text-[12.5px]">{m.primary?.organization.phone || '—'}</span></Prop>
              <Prop label="За месяц">
                <span className={repeats > 2 ? 'text-danger' : undefined}>
                  {repeats} {repeats > 2 && '· повторное'}
                </span>
              </Prop>
            </>
          )}
        </div>

        <Block title="Фотофиксация" aside={!inc.media.photoAfterUrl && <AiToggle checked={m.showAi} onChange={m.setShowAi} />}>
          <PhotoEvidence incident={inc} variant="pro" showAi={m.showAi} />
        </Block>

        <Block title="Ответственные">
          <ResponsiblesList incident={inc} variant="pro" />
        </Block>

        <Block title="Активность">
          <HistoryList history={inc.timeline.history} variant="pro" />
        </Block>
      </div>

      <footer className="shrink-0 border-t border-border px-5 py-3.5">
        <CardActions incident={inc} role={role} variant="pro" h={m.handlers} />
      </footer>
    </article>
  );
};

import React from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useFilterStore, useFilteredIncidents, hasActiveFilters } from '@/entities/incident/model/filterStore';
import { useAuthStore } from '@/entities/user/model/authStore';
import type { IncidentStatus } from '@/entities/incident/types';
import { STATUS_META, STATUS_ORDER, formatDate, lowerFirst, typoQuotes } from '@/entities/incident/lib/presentation';
import { getPrimaryOrganizationName, getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { summarizeIncidents } from '@/entities/incident/lib/summary';
import { bySource, countByStatus, createdWithin, failingExecutors, repeatAddresses } from '@/entities/incident/lib/insights';
import { DossierCard } from '@/entities/incident/ui/card/DossierCard';
import { useNow, plural } from '@/shared/lib/time';
import { MapRadar } from '@/widgets/map-radar';
import { DashboardPage } from '../../DashboardPage/DashboardPage';
import { ROLE_TITLE, issueNumber, type AppTab, APP_TABS, useUrlState } from './shared';

// ─────────────────────────────────────────────────────────────────────────────
// «Досье» — оперативная сводка в газетной манере. Мастхед с номером выпуска,
// «главное» крупными цифрами с подводкой, карта как иллюстрация с подписью,
// ведомость обращений линейками, справа — служебная записка по делу.
// ─────────────────────────────────────────────────────────────────────────────

const Rule: React.FC<{ double?: boolean; className?: string }> = ({ double, className = '' }) => (
  <div className={`${double ? 'h-[5px] border-y border-foreground' : 'h-px bg-foreground'} ${className}`} />
);

const Masthead: React.FC<{ tab: AppTab; onTab: (t: AppTab) => void; now: number }> = ({ tab, onTab, now }) => {
  const user = useAuthStore((s) => s.currentUser);
  const date = new Date(now).toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  return (
    <header className="mx-auto w-full max-w-[1440px] px-4 pt-5 md:px-8">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 pb-2 text-[12px] text-muted-foreground">
        <span className="eyebrow !text-[10.5px]">Департамент развития территории · г. Липецк</span>
        <span>
          Выпуск № {issueNumber(now)} · <span className="first-letter:uppercase">{date}</span>
        </span>
      </div>
      <Rule double />
      <div className="py-4 text-center md:py-5">
        <h1 className="font-display m-0 text-[34px] font-bold leading-none tracking-[0.02em] text-foreground md:text-[52px]">
          Чистый Липецк
        </h1>
        <p className="font-display m-0 mt-2 text-[15px] italic text-muted-foreground md:text-[17px]">
          Оперативная сводка о содержании контейнерных площадок
        </p>
      </div>
      <Rule />
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-2">
        <nav className="flex gap-6" aria-label="Разделы">
          {([
            ['map_view', 'Сводка'],
            ['analytics', 'Аналитика'],
          ] as const).map(([id, title]) => (
            <button
              key={id}
              type="button"
              onClick={() => onTab(id)}
              aria-current={tab === id ? 'page' : undefined}
              className={`eyebrow cursor-pointer !text-[11.5px] transition-colors ${
                tab === id ? '!text-foreground underline decoration-[1.5px] underline-offset-[6px]' : 'hover:!text-foreground'
              }`}
            >
              {title}
            </button>
          ))}
        </nav>
        {user && (
          <span className="font-display text-[13.5px] italic text-muted-foreground">
            Для служебного пользования · {user.name}, {lowerFirst(ROLE_TITLE[user.role])}
          </span>
        )}
      </div>
      <Rule double />
    </header>
  );
};

/* ── Главное: подводка и крупные цифры ─────────────────────────────────── */

const Lead: React.FC<{ now: number }> = ({ now }) => {
  const all = useIncidentStore((s) => s.incidents);
  const s = summarizeIncidents(all, now);
  const fresh = createdWithin(all, 24, now);
  const inWork = all.filter((i) => i.status === 'IN_PROGRESS').length;

  const figures = [
    { value: s.open, label: plural(s.open, 'открытое обращение', 'открытых обращения', 'открытых обращений') },
    { value: s.fresh, label: 'ждут проверки инспектора' },
    { value: s.overdue, label: 'срок устранения истёк', alarm: true },
    { value: s.knm, label: 'передано на КНМ', alarm: true },
  ];

  return (
    <section className="grid grid-cols-1 gap-6 py-6 lg:grid-cols-12 lg:gap-8">
      <div className="lg:col-span-5">
        <div className="eyebrow mb-2 !text-[10.5px] text-danger">Главное за сутки</div>
        <p className="font-display m-0 text-[19px] leading-[1.45] text-foreground first-letter:float-left first-letter:mr-2 first-letter:text-[58px] first-letter:font-bold first-letter:leading-[0.85]">
          Поступило за сутки {fresh} {plural(fresh, 'обращение', 'обращения', 'обращений')}. У исполнителей в работе{' '}
          {inWork} {plural(inWork, 'дело', 'дела', 'дел')}
          {s.overdue > 0 ? `, по ${s.overdue} из них срок устранения уже истёк` : ', сроки соблюдаются'}.{' '}
          {s.knm > 0
            ? `На контрольно-надзорное мероприятие ${plural(s.knm, 'передано', 'передано', 'передано')} ${s.knm} ${plural(s.knm, 'дело', 'дела', 'дел')}.`
            : 'Передач на контрольно-надзорное мероприятие нет.'}
        </p>
      </div>
      <dl className="m-0 grid grid-cols-2 lg:col-span-7 lg:grid-cols-4">
        {figures.map((f, k) => (
          <div
            key={f.label}
            className={`px-4 py-2 ${k % 2 ? 'border-l border-border' : ''} lg:border-l lg:border-border ${k === 0 ? 'lg:border-l-0 lg:pl-0' : ''} ${k > 1 ? 'max-lg:mt-4' : ''}`}
          >
            <dd className={`font-display m-0 text-[54px] font-bold leading-none ${f.alarm && f.value > 0 ? 'text-danger' : 'text-foreground'}`}>
              {f.value}
            </dd>
            <dt className="mt-2 text-[13px] leading-snug text-muted-foreground">{f.label}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
};

/* ── Ведомость обращений ───────────────────────────────────────────────── */

const Ledger: React.FC = () => {
  const { selectedIncident, selectIncident } = useIncidentStore();
  const filters = useFilterStore();
  const forCounts = useFilteredIncidents({ ignoreStatus: true });
  const list = useFilteredIncidents();
  const counts = countByStatus(forCounts);

  const opt = (id: 'all' | IncidentStatus, label: string, n: number) => (
    <button
      key={id}
      type="button"
      onClick={() => filters.set({ status: id })}
      aria-pressed={filters.status === id}
      className={`cursor-pointer whitespace-nowrap transition-colors ${
        filters.status === id ? 'font-semibold text-foreground underline decoration-[1.5px] underline-offset-4' : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      {lowerFirst(label)} <span className="font-display">({n})</span>
    </button>
  );

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b-2 border-foreground pb-1.5">
        <h2 className="font-display m-0 text-[22px] font-bold text-foreground">
          <span className="mr-2 font-normal text-muted-foreground">§ 2.</span>Ведомость обращений
        </h2>
        <span className="font-display text-[14px] italic text-muted-foreground">
          {list.length} {plural(list.length, 'запись', 'записи', 'записей')}
          {hasActiveFilters(filters) && (
            <>
              {' · '}
              <button type="button" onClick={filters.reset} className="cursor-pointer underline underline-offset-2 hover:text-foreground">
                сбросить отбор
              </button>
            </>
          )}
        </span>
      </div>

      <div className="flex flex-col gap-3 border-b border-border py-3 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13.5px]">
          <span className="eyebrow !text-[10.5px]">Показать:</span>
          {opt('all', 'Все', forCounts.length)}
          {STATUS_ORDER.map((s) => opt(s, STATUS_META[s].short, counts[s]))}
        </div>
        <input
          value={filters.query}
          onChange={(e) => filters.set({ query: e.target.value })}
          placeholder="Поиск по адресу…"
          aria-label="Поиск по адресу"
          className="font-display h-8 w-full border-0 border-b border-foreground/40 bg-transparent px-0 text-[15px] italic text-foreground outline-none placeholder:text-muted-foreground/80 focus:border-foreground md:w-60"
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] border-collapse text-[14px]">
          <thead>
            <tr className="eyebrow !text-[10.5px] text-left">
              <th className="py-2 pr-3 font-medium">№</th>
              <th className="py-2 pr-3 font-medium">Адрес</th>
              <th className="py-2 pr-3 font-medium">Ответственный</th>
              <th className="py-2 pr-3 font-medium">Стадия</th>
              <th className="py-2 pr-3 text-right font-medium" title="Нарушений на адресе за месяц">Повт.</th>
              <th className="py-2 text-right font-medium">Поступило</th>
            </tr>
          </thead>
          <tbody>
            {list.length === 0 && (
              <tr>
                <td colSpan={6} className="font-display py-8 text-center italic text-muted-foreground">
                  По заданному отбору записей нет.
                </td>
              </tr>
            )}
            {list.map((i) => {
              const selected = selectedIncident?.id === i.id;
              const repeats = getRecidivismCount(i);
              return (
                <tr
                  key={i.id}
                  onClick={() => selectIncident(i.id)}
                  aria-selected={selected}
                  className={`cursor-pointer border-t border-dotted border-foreground/25 transition-colors ${selected ? 'bg-secondary' : 'hover:bg-muted'}`}
                >
                  <td className="font-display py-2.5 pr-3 text-muted-foreground">
                    {selected && <span className="mr-1 text-foreground">▸</span>}
                    {i.id}
                  </td>
                  <td className="py-2.5 pr-3 font-medium text-foreground">{i.location.address}</td>
                  <td className="whitespace-nowrap py-2.5 pr-3 text-foreground/85">{typoQuotes(getPrimaryOrganizationName(i))}</td>
                  <td className="py-2.5 pr-3">
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[11.5px] font-semibold uppercase tracking-[0.1em]" style={{ color: STATUS_META[i.status].text }}>
                      <span className="size-2" style={{ background: STATUS_META[i.status].dot }} />
                      {STATUS_META[i.status].label}
                    </span>
                  </td>
                  <td className={`font-display py-2.5 pr-3 text-right ${repeats > 2 ? 'font-bold text-danger' : 'text-foreground'}`}>
                    {repeats > 0 ? repeats : '—'}
                  </td>
                  <td className="font-display whitespace-nowrap py-2.5 text-right text-muted-foreground">{formatDate(i.timeline.createdAt)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
};

/* ── Колонка: отстающие, повторы, источники ────────────────────────────── */

const Column: React.FC<{ now: number }> = ({ now }) => {
  const all = useIncidentStore((s) => s.incidents);
  const selectIncident = useIncidentStore((s) => s.selectIncident);
  const failing = failingExecutors(all, now).slice(0, 5);
  const repeats = repeatAddresses(all, 5);
  const sources = bySource(all).slice(0, 5);

  return (
    <div className="bg-card px-6 py-6 shadow-[var(--panel-shadow)] ring-1 ring-border">
      <div className="eyebrow !text-[10.5px]">Колонка дня</div>
      <h2 className="font-display m-0 mt-1 text-[24px] font-bold leading-tight text-foreground">Кто срывает сроки</h2>
      <p className="font-display m-0 mt-1 text-[14.5px] italic text-muted-foreground">
        Исполнители, у которых истёк срок устранения или дело ушло на КНМ.
      </p>
      {failing.length === 0 ? (
        <p className="font-display mt-4 italic text-success">Срывов сроков нет.</p>
      ) : (
        <ol className="m-0 mt-4 list-none p-0">
          {failing.map((f, k) => (
            <li key={f.name} className="flex items-baseline gap-3 border-t border-border py-2.5 first:border-t-0">
              <span className="font-display w-5 shrink-0 text-[20px] font-bold leading-none text-muted-foreground">{k + 1}</span>
              <span className="min-w-0 flex-1 text-[14.5px] text-foreground">{f.name}</span>
              <span className="font-display shrink-0 text-[14px] text-muted-foreground">
                {f.overdue > 0 && <>истёк срок — <b className="text-foreground">{f.overdue}</b></>}
                {f.overdue > 0 && f.knm > 0 && ', '}
                {f.knm > 0 && <>КНМ — <b className="text-danger">{f.knm}</b></>}
              </span>
            </li>
          ))}
        </ol>
      )}

      <h3 className="font-display m-0 mt-7 border-t-2 border-foreground pt-3 text-[18px] font-bold text-foreground">Адреса с повторами</h3>
      {repeats.length === 0 ? (
        <p className="font-display mt-2 italic text-muted-foreground">Повторных нарушений за месяц нет.</p>
      ) : (
        <ul className="m-0 mt-2 list-none p-0">
          {repeats.map((r) => (
            <li key={r.id}>
              <button type="button" onClick={() => selectIncident(r.id)} className="flex w-full cursor-pointer items-baseline gap-2 py-1.5 text-left text-[14.5px] hover:underline">
                <span className="min-w-0 flex-1 text-foreground">{r.address}</span>
                <span className="min-w-6 flex-1 translate-y-[-3px] border-b border-dotted border-foreground/35" />
                <span className="font-display font-bold text-danger">{r.count} раз</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <h3 className="font-display m-0 mt-7 border-t-2 border-foreground pt-3 text-[18px] font-bold text-foreground">Откуда поступают</h3>
      <ul className="m-0 mt-2 list-none space-y-1.5 p-0 text-[14px]">
        {sources.map((s) => (
          <li key={s.source} className="grid grid-cols-[1fr_auto] items-center gap-x-3">
            <span className="text-foreground">{s.title}</span>
            <span className="font-display text-muted-foreground">{s.count}</span>
            <span className="col-span-2 mt-0.5 h-[3px] bg-secondary">
              <span className="block h-full bg-primary" style={{ width: `${(s.count / Math.max(1, sources[0].count)) * 100}%` }} />
            </span>
          </li>
        ))}
      </ul>

      <p className="font-display mb-0 mt-7 border-t border-border pt-3 text-[13.5px] italic text-muted-foreground">
        Выберите строку ведомости или точку на карте — здесь откроется служебная записка по делу.
      </p>
    </div>
  );
};

/* ── Раскладка ──────────────────────────────────────────────────────────── */

export const DossierLayout: React.FC = () => {
  const [tab, setTab] = useUrlState<AppTab>('map_view', APP_TABS);
  const now = useNow(60_000);
  const user = useAuthStore((s) => s.currentUser);
  const selected = useIncidentStore((s) => s.selectedIncident);

  return (
    <div className="h-full overflow-y-auto">
      <Masthead tab={tab} onTab={setTab} now={now} />

      {tab === 'analytics' ? (
        <div className="mx-auto max-w-[1440px] md:px-4">
          <DashboardPage />
        </div>
      ) : (
        <main className="mx-auto w-full max-w-[1440px] px-4 pb-16 md:px-8">
          <Lead now={now} />
          <Rule />

          <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-12">
            <div className="flex min-w-0 flex-col gap-8 lg:col-span-7">
              <figure className="m-0">
                <div className="flex items-baseline justify-between border-b-2 border-foreground pb-1.5">
                  <h2 className="font-display m-0 text-[22px] font-bold text-foreground">
                    <span className="mr-2 font-normal text-muted-foreground">§ 1.</span>Карта нарушений
                  </h2>
                </div>
                <div className="mt-3 bg-card p-1.5 ring-1 ring-border">
                  <MapRadar chrome={false} className="h-[360px] w-full md:h-[420px]" />
                </div>
                <figcaption className="font-display mt-2 text-[13.5px] italic text-muted-foreground">
                  Илл. 1. Обращения на карте города. Цвет отметки — стадия:{' '}
                  {STATUS_ORDER.map((s, k) => (
                    <span key={s} className="whitespace-nowrap not-italic">
                      <span className="mr-1 inline-block size-2 align-middle" style={{ background: STATUS_META[s].dot }} />
                      <span className="italic">{lowerFirst(STATUS_META[s].label)}</span>
                      {k < STATUS_ORDER.length - 1 ? ', ' : '.'}
                    </span>
                  ))}{' '}
                  Контуры — зоны ответственности управляющих компаний.
                </figcaption>
              </figure>

              <Ledger />
            </div>

            <aside
              className={`lg:col-span-5 ${
                selected ? 'max-lg:fixed max-lg:inset-0 max-lg:z-40 max-lg:bg-background/70 max-lg:p-2 max-lg:backdrop-blur-sm' : ''
              }`}
            >
              <div className={`lg:sticky lg:top-4 ${selected ? 'max-lg:h-full lg:h-[calc(100dvh-7rem)]' : ''}`}>
                {selected && user ? <DossierCard role={user.role} /> : <Column now={now} />}
              </div>
            </aside>
          </div>
        </main>
      )}
    </div>
  );
};

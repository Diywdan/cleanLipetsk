import React, { Suspense, lazy, useMemo } from 'react';
import { Search, X, Radio, AlertTriangle, Repeat2, Hourglass } from 'lucide-react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useFilterStore, useFilteredIncidents } from '@/entities/incident/model/filterStore';
import { useAuthStore } from '@/entities/user/model/authStore';
import type { IIncident, IncidentStatus } from '@/entities/incident/types';
import { STATUS_META, STATUS_ORDER, typoQuotes } from '@/entities/incident/lib/presentation';
import { getPrimaryOrganizationName, getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { summarizeIncidents } from '@/entities/incident/lib/summary';
import { byDay, countByStatus, createdWithin, dueSoon, failingExecutors, repeatAddresses } from '@/entities/incident/lib/insights';
import { StatusIcon } from '@/entities/incident/ui/StatusIcon';
import { DispatchCard } from '@/entities/incident/ui/card/DispatchCard';
import { useNow, timeAgo, timeLeft } from '@/shared/lib/time';
import { MapRadar } from '@/widgets/map-radar';
import { ROLE_TITLE, initials, type AppTab, APP_TABS, useUrlState } from './shared';

// Аналитика с графиками (recharts) грузится, только когда её открыли
const DashboardPage = lazy(() => import('../../DashboardPage/DashboardPage').then((m) => ({ default: m.DashboardPage })));

// ─────────────────────────────────────────────────────────────────────────────
// «Диспетчерская» — ситуационный центр. Карта города на весь экран, поверх неё
// стеклянные панели: слева обстановка и лента обращений, справа дело или
// «внимание» — кто срывает сроки и где нарушения повторяются.
// На узком экране панели встают под карту обычным столбцом.
// ─────────────────────────────────────────────────────────────────────────────

const Glass: React.FC<{ className?: string; children: React.ReactNode }> = ({ className = '', children }) => (
  <div className={`glass rounded-2xl ${className}`}>{children}</div>
);

// Знак: кольцо с точкой — «объект под наблюдением»
const Mark: React.FC = () => (
  <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden className="shrink-0 drop-shadow-[0_0_10px_var(--primary)]">
    <circle cx="15" cy="15" r="12.5" fill="none" stroke="var(--primary)" strokeOpacity="0.35" strokeWidth="1" />
    <circle cx="15" cy="15" r="8" fill="none" stroke="var(--primary)" strokeWidth="1.6" strokeDasharray="3 2.2" />
    <circle cx="15" cy="15" r="3" fill="var(--primary)" />
  </svg>
);

const Clock: React.FC = () => {
  const now = useNow(1000);
  const d = new Date(now);
  return (
    <div className="flex items-center gap-3">
      <span className="hidden items-center gap-1.5 text-[11px] font-semibold tracking-[0.18em] text-success sm:flex">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60 motion-reduce:animate-none" />
          <span className="relative inline-flex size-2 rounded-full bg-success" />
        </span>
        В ЭФИРЕ
      </span>
      <div className="text-right leading-tight">
        <div className="font-num text-[17px] font-medium tracking-wide text-foreground">
          {d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
          <span className="hidden text-muted-foreground sm:inline">:{String(d.getSeconds()).padStart(2, '0')}</span>
        </div>
        <div className="hidden text-[11px] text-muted-foreground sm:block">
          {d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' })}
        </div>
      </div>
    </div>
  );
};

const TopBar: React.FC<{ tab: AppTab; onTab: (t: AppTab) => void }> = ({ tab, onTab }) => {
  const user = useAuthStore((s) => s.currentUser);
  return (
    <Glass className="pointer-events-auto flex items-center gap-3 px-3 py-2.5 sm:gap-4 sm:px-4 md:gap-6">
      <div className="flex items-center gap-3">
        <Mark />
        <div className="hidden leading-tight sm:block">
          <div className="eyebrow !text-[10px] !tracking-[0.24em] text-primary/90">Чистый Липецк</div>
          <div className="text-[15px] font-semibold text-foreground">Ситуационный центр</div>
        </div>
      </div>
      <nav className="flex rounded-full bg-[var(--inset)] p-1 ring-1 ring-border" aria-label="Разделы">
        {([
          ['map_view', 'Обстановка'],
          ['analytics', 'Аналитика'],
        ] as const).map(([id, title]) => (
          <button
            key={id}
            type="button"
            onClick={() => onTab(id)}
            aria-current={tab === id ? 'page' : undefined}
            className={`cursor-pointer rounded-full px-3 py-1 text-[13px] transition-all sm:px-3.5 ${
              tab === id
                ? 'bg-primary font-semibold text-primary-foreground shadow-[0_0_20px_-4px_var(--primary)]'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {title}
          </button>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-4">
        <Clock />
        {user && (
          <div className="hidden items-center gap-2.5 border-l border-border pl-4 lg:flex">
            <div className="text-right leading-tight">
              <div className="text-[13px] font-medium text-foreground">{user.name}</div>
              <div className="text-[11.5px] text-muted-foreground">{ROLE_TITLE[user.role]}</div>
            </div>
            <div className="grid size-8 place-items-center rounded-full bg-secondary text-[12px] font-semibold text-secondary-foreground ring-1 ring-primary/30">
              {initials(user.name)}
            </div>
          </div>
        )}
      </div>
    </Glass>
  );
};

/* ── Обстановка: четыре числа и поступление за две недели ──────────────── */

const Kpi: React.FC<{ label: string; value: number; sub?: string; color?: string }> = ({ label, value, sub, color }) => (
  <div className="rounded-xl border border-border bg-[var(--inset)] px-3 py-2.5">
    <div className="eyebrow !text-[10px]">{label}</div>
    <div
      className="font-num mt-1 text-[30px] font-medium leading-none"
      style={{ color: color ?? 'var(--foreground)', textShadow: color ? `0 0 22px ${color}` : undefined }}
    >
      {value}
    </div>
    {sub && <div className="font-num mt-1 text-[11px] text-muted-foreground">{sub}</div>}
  </div>
);

const Spark: React.FC<{ data: { label: string; total: number; closed: number }[] }> = ({ data }) => {
  const max = Math.max(1, ...data.map((d) => d.total));
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="eyebrow !text-[10px]">Поступление, 14 дней</span>
        <span className="font-num text-[11px] text-muted-foreground">
          сегодня <span className="text-primary">{data[data.length - 1]?.total ?? 0}</span>
        </span>
      </div>
      <div className="flex h-12 items-end gap-[3px]" role="img" aria-label="Поступление обращений по дням за 14 дней">
        {data.map((d, k) => (
          <div key={d.label} className="group relative flex h-full flex-1 items-end" title={`${d.label}: ${d.total}`}>
            <div
              className="w-full rounded-t-[2px] transition-colors"
              style={{
                height: `${Math.max(4, (d.total / max) * 100)}%`,
                background: k === data.length - 1 ? 'var(--primary)' : 'color-mix(in srgb, var(--primary) 38%, transparent)',
                boxShadow: k === data.length - 1 ? '0 0 12px var(--primary)' : undefined,
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
};

/* ── Лента обращений ────────────────────────────────────────────────────── */

const FeedRow: React.FC<{ incident: IIncident; now: number; selected: boolean; onSelect: () => void }> = ({
  incident,
  now,
  selected,
  onSelect,
}) => {
  const color = STATUS_META[incident.status].dot;
  const repeats = getRecidivismCount(incident);
  const left =
    incident.status === 'IN_PROGRESS' && incident.timeline.deadlineAt ? timeLeft(incident.timeline.deadlineAt, now) : null;

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected || undefined}
        className={`group relative flex w-full cursor-pointer items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
          selected ? 'bg-primary/10 ring-1 ring-primary/40' : 'hover:bg-[var(--hover)]'
        }`}
      >
        <span
          className="absolute bottom-2 left-0 top-2 w-[2px] rounded-full opacity-80"
          style={{ background: color, boxShadow: `0 0 8px ${color}` }}
        />
        <StatusIcon status={incident.status} className="mt-[3px] shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-medium text-foreground">{incident.location.address}</span>
          <span className="mt-0.5 block truncate text-[12px] text-muted-foreground">
            {typoQuotes(getPrimaryOrganizationName(incident))} · {timeAgo(incident.timeline.createdAt, now)}
          </span>
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          {left && (
            <span className={`font-num text-[11.5px] ${left.overdue ? 'text-danger' : 'text-muted-foreground'}`}>
              {left.overdue ? `−${left.text.replace('просрочено на ', '')}` : left.text}
            </span>
          )}
          {repeats > 2 && (
            <span className="font-num rounded bg-danger/15 px-1.5 text-[11px] text-danger" title="Нарушений на адресе за месяц">
              ×{repeats}
            </span>
          )}
        </span>
      </button>
    </li>
  );
};

const LeftPanel: React.FC = () => {
  const now = useNow(30_000);
  const all = useIncidentStore((s) => s.incidents);
  const { selectedIncident, selectIncident } = useIncidentStore();
  const { status, query, set } = useFilterStore();
  const forCounts = useFilteredIncidents({ ignoreStatus: true });
  const list = useFilteredIncidents();

  const summary = summarizeIncidents(all, now);
  const counts = countByStatus(forCounts);
  const days = useMemo(() => byDay(all, 14, now), [all, now]);
  const fresh24 = createdWithin(all, 24, now);
  const feed = useMemo(
    () => [...list].sort((a, b) => new Date(b.timeline.createdAt).getTime() - new Date(a.timeline.createdAt).getTime()),
    [list],
  );

  const chip = (id: 'all' | IncidentStatus, label: string, n: number) => (
    <button
      key={id}
      type="button"
      onClick={() => set({ status: id })}
      aria-pressed={status === id}
      className={`flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] transition-colors ${
        status === id ? 'bg-[var(--chip-on)] text-foreground ring-1 ring-[var(--chip-ring)]' : 'text-muted-foreground hover:bg-[var(--hover)] hover:text-foreground'
      }`}
    >
      {id !== 'all' && <StatusIcon status={id} size={12} />}
      {label}
      <span className="font-num text-[11px] opacity-80">{n}</span>
    </button>
  );

  return (
    <Glass className="pointer-events-auto flex min-h-0 w-full flex-col overflow-hidden">
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between">
          <h2 className="eyebrow m-0 flex items-center gap-2 !text-foreground/80">
            <Radio className="size-3.5 text-primary" /> Обстановка
          </h2>
          <span className="font-num text-[11px] text-muted-foreground">Липецк · 19 управ</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Kpi label="Открыто" value={summary.open} sub={`+${fresh24} за сутки`} />
          <Kpi label="Ждут проверки" value={summary.fresh} color={summary.fresh ? 'var(--st-new)' : undefined} />
          <Kpi label="Срок истёк" value={summary.overdue} color={summary.overdue ? 'var(--st-work)' : undefined} />
          <Kpi label="На КНМ" value={summary.knm} color={summary.knm ? 'var(--st-knm)' : undefined} />
        </div>
        <Spark data={days} />
      </div>

      <div className="flex flex-col gap-2 border-t border-border px-4 pb-2 pt-3">
        <div className="flex items-center justify-between">
          <h2 className="eyebrow m-0 !text-foreground/80">Лента обращений</h2>
          <span className="font-num text-[11px] text-muted-foreground">{feed.length}</span>
        </div>
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => set({ query: e.target.value })}
            placeholder="Улица или дом"
            aria-label="Поиск по адресу"
            className="h-8 w-full rounded-lg border border-border bg-[var(--inset)] pl-8 pr-8 text-[13px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/60 focus:ring-2 focus:ring-primary/20"
          />
          {query && (
            <button type="button" onClick={() => set({ query: '' })} className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer text-muted-foreground hover:text-foreground" aria-label="Очистить поиск">
              <X className="size-3.5" />
            </button>
          )}
        </label>
        <div className="-mx-1 flex flex-wrap gap-1">
          {chip('all', 'Все', forCounts.length)}
          {STATUS_ORDER.map((s) => chip(s, STATUS_META[s].short, counts[s]))}
        </div>
      </div>

      <ul className="m-0 min-h-0 flex-1 list-none space-y-0.5 overflow-y-auto p-2 pt-1 max-lg:max-h-[420px]">
        {feed.length === 0 && <li className="px-3 py-6 text-center text-[13px] text-muted-foreground">Ничего не найдено</li>}
        {feed.map((i) => (
          <FeedRow key={i.id} incident={i} now={now} selected={selectedIncident?.id === i.id} onSelect={() => selectIncident(i.id)} />
        ))}
      </ul>
    </Glass>
  );
};

/* ── Внимание: исполнители со срывами и повторные адреса ────────────────── */

const AttentionPanel: React.FC = () => {
  const now = useNow(60_000);
  const all = useIncidentStore((s) => s.incidents);
  const selectIncident = useIncidentStore((s) => s.selectIncident);
  const failing = failingExecutors(all, now).slice(0, 5);
  const repeats = repeatAddresses(all, 5);
  const soon = dueSoon(all, now, 24, 5);
  const max = Math.max(1, ...failing.map((f) => f.overdue + f.knm));

  return (
    <Glass className="pointer-events-auto flex min-h-0 w-full flex-col overflow-y-auto p-4">
      <h2 className="eyebrow m-0 flex items-center gap-2 !text-foreground/80">
        <AlertTriangle className="size-3.5 text-danger" /> Требует внимания
      </h2>

      <section className="mt-4">
        <h3 className="m-0 text-[13px] font-medium text-foreground">Сорваны сроки</h3>
        <p className="m-0 mt-0.5 text-[12px] text-muted-foreground">Просрочено в работе и передано на КНМ</p>
        {failing.length === 0 ? (
          <p className="mt-3 text-[13px] text-success">Срывов нет</p>
        ) : (
          <ul className="m-0 mt-3 list-none space-y-2.5 p-0">
            {failing.map((f) => (
              <li key={f.name}>
                <div className="flex items-baseline justify-between gap-3 text-[13px]">
                  <span className="truncate text-foreground">{f.name}</span>
                  <span className="font-num shrink-0 text-[12px]">
                    <span className="text-[var(--st-work)]">{f.overdue}</span>
                    <span className="text-muted-foreground"> · </span>
                    <span className="text-danger">{f.knm}</span>
                  </span>
                </div>
                <div className="mt-1 flex h-1 overflow-hidden rounded-full bg-[var(--inset)]">
                  <div style={{ width: `${(f.overdue / max) * 100}%`, background: 'var(--st-work)' }} />
                  <div style={{ width: `${(f.knm / max) * 100}%`, background: 'var(--st-knm)', boxShadow: '0 0 8px var(--st-knm)' }} />
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-2 flex gap-4 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-[var(--st-work)]" />срок истёк</span>
          <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-[var(--st-knm)]" />на КНМ</span>
        </div>
      </section>

      <section className="mt-6">
        <h3 className="m-0 flex items-center gap-2 text-[13px] font-medium text-foreground">
          <Hourglass className="size-3.5 text-muted-foreground" /> Срок выйдет за сутки
        </h3>
        {soon.length === 0 ? (
          <p className="mt-3 text-[13px] text-muted-foreground">Ближайшие сутки спокойно</p>
        ) : (
          <ul className="m-0 mt-2 list-none space-y-0.5 p-0">
            {soon.map((i) => {
              const left = timeLeft(i.timeline.deadlineAt!, now);
              const hot = left.ms < 4 * 3_600_000;
              return (
                <li key={i.id}>
                  <button
                    type="button"
                    onClick={() => selectIncident(i.id)}
                    className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] text-foreground">{typoQuotes(i.location.address)}</span>
                      <span className="block truncate text-[11.5px] text-muted-foreground">{typoQuotes(getPrimaryOrganizationName(i))}</span>
                    </span>
                    <span className={`font-num shrink-0 text-[12px] ${hot ? 'text-[var(--st-work)]' : 'text-muted-foreground'}`}>{left.text}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="mt-6">
        <h3 className="m-0 flex items-center gap-2 text-[13px] font-medium text-foreground">
          <Repeat2 className="size-3.5 text-muted-foreground" /> Повторяются за месяц
        </h3>
        {repeats.length === 0 ? (
          <p className="mt-3 text-[13px] text-muted-foreground">Повторных нарушений нет</p>
        ) : (
          <ul className="m-0 mt-2 list-none space-y-0.5 p-0">
            {repeats.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => selectIncident(r.id)}
                  className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                >
                  <StatusIcon status={r.status} size={12} />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{r.address}</span>
                  <span className="font-num text-[12px] text-danger">×{r.count}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="mb-0 mt-auto pt-6 text-[12px] leading-snug text-muted-foreground">
        Выберите точку на карте или строку в ленте — здесь откроется дело.
      </p>
    </Glass>
  );
};

/* ── Раскладка ──────────────────────────────────────────────────────────── */

export const DispatchLayout: React.FC = () => {
  const [tab, setTab] = useUrlState<AppTab>('map_view', APP_TABS);
  const user = useAuthStore((s) => s.currentUser);
  const selected = useIncidentStore((s) => s.selectedIncident);
  const list = useFilteredIncidents();
  const counts = countByStatus(list);

  return (
    <div className="relative h-full overflow-y-auto lg:overflow-hidden">
      {/* Фон: глубина и холодное свечение по краям */}
      <div className="pointer-events-none fixed inset-0 [background:var(--stage-glow)]" />

      <div className="relative z-20 p-3 lg:pointer-events-none lg:absolute lg:inset-x-4 lg:top-4 lg:p-0">
        <TopBar tab={tab} onTab={setTab} />
      </div>

      {tab === 'analytics' ? (
        <div className="relative z-10 h-full overflow-y-auto lg:pt-[72px]">
          <div className="mx-auto max-w-[1600px]">
            <Suspense fallback={<div className="eyebrow p-6">Загружаю аналитику…</div>}>
              <DashboardPage />
            </Suspense>
          </div>
        </div>
      ) : (
        <>
          <div className="relative isolate mx-3 h-[52vh] overflow-hidden rounded-2xl ring-1 ring-border lg:absolute lg:inset-0 lg:mx-0 lg:h-auto lg:rounded-none lg:ring-0">
            <MapRadar chrome={false} className="h-full w-full" />
            {/* Виньетка: края карты уходят в фон, панели читаются */}
            <div className="pointer-events-none absolute inset-0 shadow-[var(--vignette)]" />
            <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(var(--grid-line)_1px,transparent_1px),linear-gradient(90deg,var(--grid-line)_1px,transparent_1px)] bg-[size:48px_48px]" />
          </div>

          {/* На телефоне открытое дело — полноэкранный слой: поднимаем весь блок над шапкой и кнопками карты */}
          <div className={`relative flex flex-col gap-3 p-3 lg:pointer-events-none ${selected ? 'z-50 lg:z-10' : 'z-10'} lg:absolute lg:inset-x-4 lg:bottom-14 lg:top-[84px] lg:flex-row lg:items-stretch lg:justify-between lg:p-0`}>
            <div className="flex min-h-0 lg:w-[340px] xl:w-[372px]">
              <LeftPanel />
            </div>

            <div
              className={`flex min-h-0 lg:w-[400px] xl:w-[452px] ${
                selected ? 'max-lg:fixed max-lg:inset-0 max-lg:z-40 max-lg:bg-background/70 max-lg:p-2 max-lg:backdrop-blur-sm' : ''
              }`}
            >
              {selected && user ? (
                <Glass className="pointer-events-auto flex min-h-0 w-full flex-col overflow-hidden max-lg:max-h-none">
                  <DispatchCard role={user.role} />
                </Glass>
              ) : (
                <AttentionPanel />
              )}
            </div>
          </div>

          {/* Нижняя полоса карты: легенда по центру, по углам — копирайт Яндекса, его закрывать нельзя */}
          <div className="pointer-events-none absolute bottom-2 left-1/2 z-10 hidden -translate-x-1/2 xl:block">
            <Glass className="pointer-events-auto rounded-full px-4 py-1.5">
              <ul className="m-0 flex list-none items-center gap-4 p-0 text-[12px] text-muted-foreground">
                {STATUS_ORDER.map((s) => (
                  <li key={s} className="flex items-center gap-1.5">
                    <span className="size-2 rounded-full" style={{ background: STATUS_META[s].dot, boxShadow: `0 0 8px ${STATUS_META[s].dot}` }} />
                    {STATUS_META[s].label}
                    <span className="font-num text-foreground">{counts[s]}</span>
                  </li>
                ))}
              </ul>
            </Glass>
          </div>
        </>
      )}
    </div>
  );
};

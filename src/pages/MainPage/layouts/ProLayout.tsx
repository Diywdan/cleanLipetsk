import React, { useEffect, useMemo, useRef } from 'react';
import { BarChart3, ChevronDown, List, Map as MapIcon, Search } from 'lucide-react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useFilterStore, useFilteredIncidents, type PeriodFilter } from '@/entities/incident/model/filterStore';
import { useAuthStore } from '@/entities/user/model/authStore';
import type { IIncident, IncidentStatus } from '@/entities/incident/types';
import { STATUS_META, STATUS_ORDER, typoQuotes } from '@/entities/incident/lib/presentation';
import { getPrimaryOrganizationName, getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { countByStatus } from '@/entities/incident/lib/insights';
import { StatusIcon } from '@/entities/incident/ui/StatusIcon';
import { ProCard } from '@/entities/incident/ui/card/ProCard';
import { useNow, timeLeft } from '@/shared/lib/time';
import { MapRadar } from '@/widgets/map-radar';
import { DashboardPage } from '../../DashboardPage/DashboardPage';
import { ROLE_TITLE, initials, useUrlState } from './shared';

// ─────────────────────────────────────────────────────────────────────────────
// «Профинструмент» — рабочее место инспектора в духе трекеров задач.
// Боковое меню по стадиям, плотный список с группами, деталь справа.
// Клавиатура: j / k или стрелки — по списку, Esc — закрыть дело, / — поиск.
// ─────────────────────────────────────────────────────────────────────────────

type View = 'list' | 'map' | 'analytics';
const VIEWS = ['list', 'map', 'analytics'] as const;

const PERIODS: { id: PeriodFilter; title: string }[] = [
  { id: 'all', title: 'За всё время' },
  { id: 'today', title: 'Сегодня' },
  { id: '3days', title: '3 дня' },
  { id: 'week', title: 'Неделя' },
];

// Приоритет — три столбика разной высоты, как в трекерах
const Priority: React.FC<{ level: IIncident['priority'] }> = ({ level }) => {
  const n = { LOW: 1, MEDIUM: 2, HIGH: 3 }[level];
  const title = { LOW: 'Низкий приоритет', MEDIUM: 'Средний приоритет', HIGH: 'Высокий приоритет' }[level];
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-label={title} role="img" className="shrink-0">
      <title>{title}</title>
      {[0, 1, 2].map((k) => (
        <rect
          key={k}
          x={1.5 + k * 4}
          y={9 - k * 3}
          width="3"
          height={4 + k * 3}
          rx="0.8"
          fill={k < n ? (level === 'HIGH' ? 'var(--warning)' : 'var(--muted-foreground)') : 'var(--border)'}
        />
      ))}
    </svg>
  );
};

const Kbd: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <kbd className="font-num rounded border border-border bg-muted px-1 text-[10.5px] leading-[16px] text-muted-foreground">{children}</kbd>
);

/* ── Боковое меню ───────────────────────────────────────────────────────── */

const NavItem: React.FC<{
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  count?: number;
}> = ({ active, onClick, icon, label, count }) => (
  <button
    type="button"
    onClick={onClick}
    aria-current={active || undefined}
    className={`flex h-8 w-full cursor-pointer items-center gap-2.5 rounded-md px-2 text-[13px] transition-colors ${
      active ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
    }`}
  >
    <span className="grid w-4 place-items-center">{icon}</span>
    <span className="flex-1 text-left">{label}</span>
    {count !== undefined && <span className="font-num text-[11.5px] text-muted-foreground">{count}</span>}
  </button>
);

const Sidebar: React.FC<{ view: View; setView: (v: View) => void; onSearch: () => void }> = ({ view, setView, onSearch }) => {
  const user = useAuthStore((s) => s.currentUser);
  const { status, set } = useFilterStore();
  const forCounts = useFilteredIncidents({ ignoreStatus: true });
  const counts = countByStatus(forCounts);

  const pick = (s: 'all' | IncidentStatus) => {
    set({ status: s });
    if (view === 'analytics') setView('list');
  };

  return (
    <aside className="hidden w-[232px] shrink-0 flex-col border-r border-border bg-[var(--sidebar)] lg:flex">
      <div className="flex h-12 items-center gap-2.5 px-3">
        <span className="grid size-[22px] place-items-center rounded-[5px] bg-primary text-[10px] font-bold text-primary-foreground">ЧЛ</span>
        <span className="text-[13.5px] font-semibold text-foreground">Чистый Липецк</span>
        <ChevronDown className="size-3.5 text-muted-foreground" />
      </div>

      <div className="px-2">
        <button
          type="button"
          onClick={onSearch}
          className="flex h-8 w-full cursor-pointer items-center gap-2.5 rounded-md border border-border px-2 text-[13px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
        >
          <Search className="size-3.5" />
          <span className="flex-1 text-left">Поиск</span>
          <Kbd>/</Kbd>
        </button>
      </div>

      <nav className="mt-4 flex flex-col gap-0.5 px-2" aria-label="Стадии">
        <div className="px-2 pb-1 text-[11.5px] font-medium text-muted-foreground">Обращения</div>
        <NavItem active={status === 'all' && view !== 'analytics'} onClick={() => pick('all')} icon={<List className="size-3.5" />} label="Все" count={forCounts.length} />
        {STATUS_ORDER.map((s) => (
          <NavItem
            key={s}
            active={status === s && view !== 'analytics'}
            onClick={() => pick(s)}
            icon={<StatusIcon status={s} />}
            label={STATUS_META[s].label}
            count={counts[s]}
          />
        ))}
      </nav>

      <nav className="mt-5 flex flex-col gap-0.5 px-2" aria-label="Виды">
        <div className="px-2 pb-1 text-[11.5px] font-medium text-muted-foreground">Виды</div>
        <NavItem active={view === 'list'} onClick={() => setView('list')} icon={<List className="size-3.5" />} label="Список" />
        <NavItem active={view === 'map'} onClick={() => setView('map')} icon={<MapIcon className="size-3.5" />} label="Карта" />
        <NavItem active={view === 'analytics'} onClick={() => setView('analytics')} icon={<BarChart3 className="size-3.5" />} label="Аналитика" />
      </nav>

      <div className="mt-auto border-t border-border p-3">
        <div className="mb-3 space-y-1.5 text-[11.5px] text-muted-foreground">
          <div className="flex items-center gap-1.5"><Kbd>j</Kbd><Kbd>k</Kbd> по списку</div>
          <div className="flex items-center gap-1.5"><Kbd>Esc</Kbd> закрыть дело</div>
        </div>
        {user && (
          <div className="flex items-center gap-2.5">
            <span className="grid size-7 place-items-center rounded-full bg-secondary text-[11px] font-semibold text-secondary-foreground">{initials(user.name)}</span>
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-[12.5px] text-foreground">{user.name}</span>
              <span className="block truncate text-[11.5px] text-muted-foreground">{ROLE_TITLE[user.role]}</span>
            </span>
          </div>
        )}
      </div>
    </aside>
  );
};

/* ── Строка списка ──────────────────────────────────────────────────────── */

const Row: React.FC<{ incident: IIncident; selected: boolean; now: number; onSelect: () => void }> = ({ incident, selected, now, onSelect }) => {
  const repeats = getRecidivismCount(incident);
  const left = incident.status === 'IN_PROGRESS' && incident.timeline.deadlineAt ? timeLeft(incident.timeline.deadlineAt, now) : null;
  return (
    <li
      data-row={incident.id}
      onClick={onSelect}
      aria-selected={selected}
      className={`group flex h-10 cursor-pointer items-center gap-3 border-b border-border/60 px-4 text-[13px] transition-colors lg:px-5 ${
        selected ? 'bg-primary/[0.09] shadow-[inset_2px_0_0_var(--primary)]' : 'hover:bg-[var(--hover)]'
      }`}
    >
      <Priority level={incident.priority} />
      <span className="font-num w-12 shrink-0 text-[12px] text-muted-foreground">{incident.id}</span>
      <StatusIcon status={incident.status} className="shrink-0" />
      <span className="min-w-0 flex-1 truncate text-foreground">{incident.location.address}</span>
      {repeats > 2 && (
        <span className="font-num shrink-0 rounded px-1.5 text-[11.5px] text-danger ring-1 ring-danger/30" title="Нарушений на адресе за месяц">
          ×{repeats}
        </span>
      )}
      <span className="hidden max-w-[200px] shrink-0 truncate rounded-full border border-border px-2 py-px text-[11.5px] text-muted-foreground md:inline">
        {typoQuotes(getPrimaryOrganizationName(incident))}
      </span>
      <span className={`font-num hidden w-[104px] shrink-0 text-right text-[11.5px] sm:inline ${left?.overdue ? 'text-danger' : 'text-muted-foreground'}`}>
        {left ? (left.overdue ? `−${left.text.replace('просрочено на ', '')}` : left.text) : ''}
      </span>
      <span className="font-num w-[52px] shrink-0 text-right text-[11.5px] text-muted-foreground">
        {new Date(incident.timeline.createdAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }).replace('.', '')}
      </span>
    </li>
  );
};

/* ── Раскладка ──────────────────────────────────────────────────────────── */

export const ProLayout: React.FC = () => {
  const [view, setView] = useUrlState<View>('list', VIEWS);
  const user = useAuthStore((s) => s.currentUser);
  const { selectedIncident, selectIncident } = useIncidentStore();
  const filters = useFilterStore();
  const list = useFilteredIncidents();
  const forCounts = useFilteredIncidents({ ignoreStatus: true });
  const counts = countByStatus(forCounts);
  const now = useNow(30_000);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Группы по стадиям, если стадия не выбрана; плоский порядок — для j/k
  const groups = useMemo(() => {
    const order = filters.status === 'all' ? STATUS_ORDER : [filters.status];
    return order
      .map((s) => ({ status: s, items: list.filter((i) => i.status === s) }))
      .filter((g) => g.items.length > 0);
  }, [list, filters.status]);
  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  // Клавиатура
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (e.key === 'Escape') {
        if (typing) (e.target as HTMLElement).blur();
        else selectIncident(null);
        return;
      }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === '/') {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      const step = e.key === 'j' || e.key === 'ArrowDown' ? 1 : e.key === 'k' || e.key === 'ArrowUp' ? -1 : 0;
      if (!step || flat.length === 0 || view !== 'list') return;
      e.preventDefault();
      const at = flat.findIndex((i) => i.id === selectedIncident?.id);
      const next = flat[Math.min(flat.length - 1, Math.max(0, at === -1 ? 0 : at + step))];
      selectIncident(next.id);
      listRef.current?.querySelector(`[data-row="${next.id}"]`)?.scrollIntoView({ block: 'nearest' });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [flat, selectedIncident, selectIncident, view]);

  const title = filters.status === 'all' ? 'Все обращения' : STATUS_META[filters.status].label;

  return (
    <div className="flex h-full" style={{ fontFeatureSettings: '"cv11", "ss01"' }}>
      <Sidebar view={view} setView={setView} onSearch={() => { setView(view === 'analytics' ? 'list' : view); setTimeout(() => searchRef.current?.focus(), 0); }} />

      <div className="flex min-w-0 flex-1 flex-col">
        {view === 'analytics' ? (
          <>
            <div className="flex h-12 shrink-0 items-center gap-3 border-b border-border px-4 lg:px-5">
              <span className="text-[13.5px] font-medium text-foreground">Аналитика</span>
              <button type="button" onClick={() => setView('list')} className="ml-auto cursor-pointer text-[12.5px] text-muted-foreground hover:text-foreground lg:hidden">
                К списку
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <DashboardPage />
            </div>
          </>
        ) : (
          <>
            {/* Панель инструментов */}
            <div className="flex h-12 shrink-0 items-center gap-3 border-b border-border px-4 lg:px-5">
              <span className="flex items-center gap-2 text-[13.5px] font-medium text-foreground">
                {filters.status !== 'all' && <StatusIcon status={filters.status} />}
                {title}
                <span className="font-num text-[12px] font-normal text-muted-foreground">{list.length}</span>
              </span>
              <div className="ml-auto flex items-center gap-2">
                <label className="relative hidden sm:block">
                  <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <input
                    ref={searchRef}
                    value={filters.query}
                    onChange={(e) => filters.set({ query: e.target.value })}
                    placeholder="Адрес"
                    aria-label="Поиск по адресу"
                    className="h-7 w-44 rounded-md border border-border bg-transparent pl-7 pr-2 text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/60 focus:ring-2 focus:ring-primary/20 lg:w-56"
                  />
                </label>
                <select
                  value={filters.period}
                  onChange={(e) => filters.set({ period: e.target.value as PeriodFilter })}
                  aria-label="Период поступления"
                  className="h-7 cursor-pointer rounded-md border border-border bg-card px-2 text-[12.5px] text-foreground outline-none focus:border-primary/60"
                >
                  {PERIODS.map((p) => (
                    <option key={p.id} value={p.id}>{p.title}</option>
                  ))}
                </select>
                <div className="flex rounded-md border border-border p-0.5" role="radiogroup" aria-label="Вид">
                  {([
                    ['list', <List key="l" className="size-3.5" />, 'Список'],
                    ['map', <MapIcon key="m" className="size-3.5" />, 'Карта'],
                  ] as const).map(([id, icon, label]) => (
                    <button
                      key={id}
                      type="button"
                      role="radio"
                      aria-checked={view === id}
                      title={label}
                      onClick={() => setView(id)}
                      className={`grid h-6 w-7 cursor-pointer place-items-center rounded transition-colors ${view === id ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                    >
                      {icon}
                    </button>
                  ))}
                </div>
                <button type="button" onClick={() => setView('analytics')} className="grid h-7 w-7 cursor-pointer place-items-center rounded-md border border-border text-muted-foreground hover:text-foreground lg:hidden" title="Аналитика" aria-label="Аналитика">
                  <BarChart3 className="size-3.5" />
                </button>
              </div>
            </div>

            {/* Стадии на узком экране — вместо бокового меню */}
            <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-border px-3 py-2 lg:hidden">
              {(['all', ...STATUS_ORDER] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => filters.set({ status: s })}
                  aria-pressed={filters.status === s}
                  className={`flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] ${filters.status === s ? 'bg-accent text-foreground' : 'text-muted-foreground'}`}
                >
                  {s !== 'all' && <StatusIcon status={s} size={12} />}
                  {s === 'all' ? 'Все' : STATUS_META[s].short}
                  <span className="font-num text-[11px]">{s === 'all' ? forCounts.length : counts[s]}</span>
                </button>
              ))}
            </div>

            {view === 'map' ? (
              <div className="relative min-h-0 flex-1">
                <MapRadar chrome={false} className="absolute inset-0" />
              </div>
            ) : (
              <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto">
                {groups.length === 0 && (
                  <div className="grid h-48 place-items-center text-[13px] text-muted-foreground">Нет обращений с такими условиями</div>
                )}
                {groups.map((g) => (
                  <section key={g.status}>
                    <h3 className="sticky top-0 z-10 m-0 flex h-9 items-center gap-2 border-b border-border bg-[var(--group-bg)] px-4 text-[12.5px] font-medium text-foreground lg:px-5">
                      <StatusIcon status={g.status} />
                      {STATUS_META[g.status].label}
                      <span className="font-num font-normal text-muted-foreground">{g.items.length}</span>
                    </h3>
                    <ul className="m-0 list-none p-0">
                      {g.items.map((i) => (
                        <Row key={i.id} incident={i} now={now} selected={selectedIncident?.id === i.id} onSelect={() => selectIncident(i.id)} />
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {selectedIncident && user && view !== 'analytics' && (
        <div className="fixed inset-0 z-40 bg-background lg:static lg:z-auto lg:w-[440px] lg:shrink-0 lg:border-l lg:border-border xl:w-[480px]">
          <ProCard role={user.role} />
        </div>
      )}
    </div>
  );
};

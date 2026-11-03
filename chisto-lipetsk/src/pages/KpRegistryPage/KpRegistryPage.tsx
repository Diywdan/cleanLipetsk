import React, { useMemo, useState } from 'react';
import { ArrowLeft, BadgeCheck, CircleAlert, MapPin, Search, X } from 'lucide-react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useKpStore } from '@/entities/kp/model/kpStore';
import type { IKpCard, KpDataSource } from '@/entities/kp/types';
import { incidentsOfKp, kpStats, type KpStats } from '@/entities/kp/lib/registry';
import { ORGANIZATION_KIND_TITLE, RESPONSIBLE_ROLE_TITLE } from '@/entities/incident/lib/responsibles';
import { formatDate, formatDateTime, typoQuotes } from '@/entities/incident/lib/presentation';
import { StatusTag } from '@/entities/incident/ui/StatusTag';
import { useNow, plural } from '@/shared/lib/time';

// ─────────────────────────────────────────────────────────────────────────────
// Реестр контейнерных площадок: справочник КП и история нарушений по каждой.
// Слева список с поиском, справа карточка площадки; «Открыть дело» переводит
// в «Обстановку» с открытой карточкой обращения.
// ─────────────────────────────────────────────────────────────────────────────

const Glass: React.FC<{ className?: string; children: React.ReactNode }> = ({ className = '', children }) => (
  <div className={`glass rounded-2xl ${className}`}>{children}</div>
);

const SURFACE: Record<NonNullable<IKpCard['surface']>, string> = { ASPHALT: 'асфальт', CONCRETE: 'бетон', SOIL: 'грунт' };
const DATA_SOURCE: Record<KpDataSource, string> = {
  FGIS_UTKO: 'ФГИС УТКО',
  FIELD_CHECK: 'полевая проверка',
  MANUAL: 'из обращения, не сверено',
};

type Filter = 'all' | 'open' | 'unconfirmed';
type Row = { kp: IKpCard; stats: KpStats; unconfirmed: boolean };

function readKpFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get('kp');
}
function writeKpToUrl(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set('kp', id);
  else url.searchParams.delete('kp');
  window.history.replaceState(null, '', url);
}

export const KpRegistryPage: React.FC<{ onOpenIncident: (id: string) => void }> = ({ onOpenIncident }) => {
  const cards = useKpStore((s) => s.cards);
  const loadError = useKpStore((s) => s.error);
  const incidents = useIncidentStore((s) => s.incidents);
  const now = useNow(60_000);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(readKpFromUrl);

  const select = (id: string | null) => {
    setSelectedId(id);
    writeKpToUrl(id);
  };

  const rows: Row[] = useMemo(
    () =>
      cards
        .map((kp) => ({ kp, stats: kpStats(kp.id, incidents, now), unconfirmed: kp.responsibles.some((r) => !r.confirmed) }))
        .sort((a, b) => b.stats.last30 - a.stats.last30 || b.stats.open - a.stats.open || a.kp.code.localeCompare(b.kp.code)),
    [cards, incidents, now],
  );

  const q = query.trim().toLowerCase();
  const visible = rows.filter(
    (r) =>
      (filter === 'all' || (filter === 'open' ? r.stats.open > 0 : r.unconfirmed)) &&
      (!q ||
        r.kp.location.address.toLowerCase().includes(q) ||
        r.kp.code.toLowerCase().includes(q) ||
        (r.kp.registryNumber ?? '').includes(q)),
  );
  const selected = rows.find((r) => r.kp.id === selectedId) ?? null;
  const repeat = rows.filter((r) => r.stats.last30 > 2).length;
  const unconfirmed = rows.filter((r) => r.unconfirmed).length;

  const chips: { id: Filter; title: string; n: number }[] = [
    { id: 'all', title: 'Все', n: rows.length },
    { id: 'open', title: 'С открытыми делами', n: rows.filter((r) => r.stats.open > 0).length },
    { id: 'unconfirmed', title: 'Ответственный не подтверждён', n: unconfirmed },
  ];

  return (
    <div className="flex flex-col gap-3 p-3 lg:h-full lg:min-h-0 lg:flex-row lg:p-4">
      {/* ── Список ── */}
      <Glass className={`flex min-h-0 flex-col lg:w-[420px] lg:shrink-0 ${selected ? 'max-lg:hidden' : ''}`}>
        <div className="border-b border-border p-4">
          <h2 className="eyebrow m-0 !text-foreground/80">Реестр площадок</h2>
          <p className="m-0 mt-1.5 text-[13px] text-muted-foreground">
            {rows.length} {plural(rows.length, 'площадка', 'площадки', 'площадок')} ·{' '}
            <span className={repeat ? 'text-danger' : ''}>{repeat} с повторными нарушениями</span> · {unconfirmed} без подтверждённого ответственного
          </p>
          <label className="mt-3 flex items-center gap-2 rounded-lg bg-[var(--inset)] px-3 py-2 ring-1 ring-border focus-within:ring-primary">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Адрес, код LP- или номер реестра"
              className="min-w-0 flex-1 bg-transparent text-[14px] text-foreground outline-none placeholder:text-muted-foreground"
            />
            {query && (
              <button type="button" onClick={() => setQuery('')} aria-label="Очистить поиск" className="cursor-pointer text-muted-foreground hover:text-foreground">
                <X className="size-4" />
              </button>
            )}
          </label>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {chips.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setFilter(c.id)}
                aria-pressed={filter === c.id}
                className={`cursor-pointer rounded-full px-2.5 py-1 text-[12.5px] ring-1 transition-colors ${
                  filter === c.id ? 'bg-primary/15 text-foreground ring-primary/50' : 'text-muted-foreground ring-border hover:text-foreground'
                }`}
              >
                {c.title} <span className="font-num opacity-70">{c.n}</span>
              </button>
            ))}
          </div>
        </div>

        {loadError && <p className="m-0 p-4 text-[13px] text-danger">{loadError}</p>}
        <ul className="m-0 min-h-0 flex-1 list-none overflow-y-auto p-2">
          {visible.map(({ kp, stats, unconfirmed: unconf }) => (
            <li key={kp.id}>
              <button
                type="button"
                onClick={() => select(kp.id)}
                aria-current={selectedId === kp.id ? 'true' : undefined}
                className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                  selectedId === kp.id ? 'bg-primary/10 ring-1 ring-primary/40' : 'hover:bg-[var(--hover)]'
                }`}
              >
                <span className="min-w-0 flex-1">
                  <span className="font-num block text-[11.5px] text-muted-foreground">{kp.code}</span>
                  <span className="block truncate text-[14px] font-medium text-foreground">{kp.location.address}</span>
                  <span className="flex items-center gap-1 truncate text-[12px] text-muted-foreground">
                    {unconf && <CircleAlert className="size-3 shrink-0 text-[var(--st-work)]" aria-label="Ответственный не подтверждён" />}
                    {typoQuotes(kp.responsibles[0]?.organization.name ?? 'ответственный не указан')}
                  </span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-1">
                  <span
                    className={`font-num rounded-md px-1.5 text-[13px] ${stats.last30 > 2 ? 'bg-[var(--st-knm-bg)] text-danger' : 'text-muted-foreground'}`}
                    title="Обращений за 30 дней"
                  >
                    {stats.last30}
                  </span>
                  {stats.open > 0 && <span className="text-[11px] text-[var(--st-work)]">открыто {stats.open}</span>}
                </span>
              </button>
            </li>
          ))}
          {visible.length === 0 && <li className="p-4 text-[13px] text-muted-foreground">Ничего не нашлось.</li>}
        </ul>
      </Glass>

      {/* ── Карточка площадки ── */}
      <Glass className={`min-h-0 flex-1 overflow-y-auto ${selected ? '' : 'max-lg:hidden'}`}>
        {selected ? (
          <KpCardView row={selected} onBack={() => select(null)} onOpenIncident={onOpenIncident} />
        ) : (
          <div className="grid h-full place-items-center p-8 text-center text-[14px] text-muted-foreground">
            Выберите площадку в списке — здесь откроется её карточка и история нарушений.
          </div>
        )}
      </Glass>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string | number; alarm?: boolean }> = ({ label, value, alarm }) => (
  <div className="rounded-lg border border-border bg-[var(--inset)] px-3 py-2.5">
    <div className="eyebrow !text-[10px]">{label}</div>
    <div className={`font-num mt-1 text-[22px] leading-none ${alarm ? 'text-danger' : 'text-foreground'}`}>{value}</div>
  </div>
);

const Fact: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex justify-between gap-4 border-b border-border py-2 text-[13.5px] last:border-b-0">
    <span className="text-muted-foreground">{label}</span>
    <span className="text-right text-foreground">{children}</span>
  </div>
);

const KpCardView: React.FC<{ row: Row; onBack: () => void; onOpenIncident: (id: string) => void }> = ({ row, onBack, onOpenIncident }) => {
  const incidents = useIncidentStore((s) => s.incidents);
  const { kp, stats } = row;
  const history = incidentsOfKp(kp.id, incidents);
  const c = kp.containers;

  return (
    <article className="p-5">
      <button type="button" onClick={onBack} className="mb-3 flex cursor-pointer items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground lg:hidden">
        <ArrowLeft className="size-4" /> К списку
      </button>
      <div className="font-num flex flex-wrap items-baseline gap-x-3 text-[13px] text-muted-foreground">
        <span className="text-[22px] font-semibold text-foreground">{kp.code}</span>
        {kp.registryNumber && <span>реестр {kp.registryNumber}</span>}
      </div>
      <h2 className="m-0 mt-2 flex items-start gap-2 text-[19px] font-semibold leading-snug text-foreground">
        <MapPin className="mt-1 size-4 shrink-0 text-primary" />
        {kp.location.address}
      </h2>
      <p className="font-num m-0 mt-1 text-[12px] text-muted-foreground">
        Управа № {kp.location.upravaId}
        {kp.location.cadastralNumber ? ` · кадастр ${kp.location.cadastralNumber}` : ''}
      </p>

      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="За 30 дней" value={stats.last30} alarm={stats.last30 > 2} />
        <Stat label="Открыто" value={stats.open} />
        <Stat label="На КНМ" value={stats.knm} alarm={stats.knm > 0} />
        <Stat label="Устраняют в среднем" value={stats.avgFixHours == null ? '—' : `${Math.round(stats.avgFixHours)} ч`} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <section>
          <h3 className="eyebrow m-0 mb-2">Ответственные</h3>
          <ul className="m-0 list-none divide-y divide-border rounded-lg border border-border p-0">
            {kp.responsibles.map((r) => (
              <li key={r.role} className="px-3 py-2.5">
                <div className="text-[12px] text-muted-foreground">{RESPONSIBLE_ROLE_TITLE[r.role]}</div>
                <div className="flex items-center gap-1.5 text-[14px] text-foreground">
                  {typoQuotes(r.organization.name)}
                  <span className="text-[12px] text-muted-foreground">· {ORGANIZATION_KIND_TITLE[r.organization.kind]}</span>
                </div>
                <div className={`mt-0.5 flex items-center gap-1 text-[12px] ${r.confirmed ? 'text-success' : 'text-[var(--st-work)]'}`}>
                  {r.confirmed ? <BadgeCheck className="size-3.5" /> : <CircleAlert className="size-3.5" />}
                  {r.confirmed ? 'подтверждено документом или проверкой' : 'не подтверждено — нужна полевая проверка'}
                </div>
                {r.organization.phone && <div className="font-num mt-0.5 text-[12px] text-muted-foreground">{r.organization.phone}</div>}
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="eyebrow m-0 mb-2">Паспорт площадки</h3>
          <div className="rounded-lg border border-border px-3">
            <Fact label="Баки ТКО">{c ? <span className="font-num">{c.tko}</span> : '—'}</Fact>
            <Fact label="Раздельный сбор">{c ? (c.separate ? <span className="font-num">{c.separate}</span> : 'нет') : '—'}</Fact>
            <Fact label="Отсек под КГМ">{c ? (c.kgmBay ? 'есть' : 'нет') : '—'}</Fact>
            <Fact label="Покрытие">{kp.surface ? SURFACE[kp.surface] : '—'}</Fact>
            <Fact label="Ограждение">{kp.fenced == null ? '—' : kp.fenced ? 'есть' : 'нет'}</Fact>
            <Fact label="Источник данных">{DATA_SOURCE[kp.dataSource]}</Fact>
            <Fact label="Последняя проверка">{kp.checkedAt ? formatDate(kp.checkedAt) : '—'}</Fact>
          </div>
        </section>
      </div>

      <section className="mt-6">
        <h3 className="eyebrow m-0 mb-2">
          История обращений · {history.length}
          {stats.falsePositive > 0 ? ` · ложных ${stats.falsePositive}` : ''}
        </h3>
        {history.length === 0 ? (
          <p className="m-0 text-[13px] text-muted-foreground">Обращений по площадке не было.</p>
        ) : (
          <ul className="m-0 list-none space-y-1 p-0">
            {history.map((i) => (
              <li key={i.id}>
                <button
                  type="button"
                  onClick={() => {
                    writeKpToUrl(null);
                    onOpenIncident(i.id);
                  }}
                  className="flex w-full cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 rounded-lg px-3 py-2 text-left ring-1 ring-border hover:bg-[var(--hover)]"
                >
                  <span className="font-num w-[136px] shrink-0 whitespace-nowrap text-[12px] text-muted-foreground">{formatDateTime(i.timeline.createdAt)}</span>
                  <span className="font-num text-[13px] text-foreground">№ {i.id}</span>
                  <StatusTag status={i.status} className="!text-[12px]" />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">
                    {i.media.boundingBoxes.map((b) => b.label).join(', ') || '—'}
                  </span>
                  <span className="text-[12px] text-primary">Открыть дело →</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
};

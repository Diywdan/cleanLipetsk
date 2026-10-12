import React, { useMemo } from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { STATUS_META, STATUS_ORDER } from '@/entities/incident/lib/presentation';
import { getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { byDay, bySource, countByStatus, executorStats, isOverdue } from '@/entities/incident/lib/insights';
import { useStandStore, type ThemeId } from '@/shared/theme/standStore';
import { useThemeColors } from '@/shared/theme/themeColors';
import { useNow } from '@/shared/lib/time';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

// Аналитика по исполнителям. Содержание одно на все темы, оформление — своё:
// gos — карточки с заголовком; dispatch — стекло и свечение; dossier — газетные
// таблицы с номерами и подписями; pro — плотные панели с тонкой рамкой.

type V = ThemeId;

const Panel: React.FC<{ v: V; n?: number; title: string; note?: string; className?: string; children: React.ReactNode }> = ({
  v,
  n,
  title,
  note,
  className = '',
  children,
}) => {
  if (v === 'dossier') {
    return (
      <section className={`flex flex-col ${className}`}>
        <div className="border-b-2 border-foreground pb-1.5">
          <h2 className="font-display m-0 text-[19px] font-bold text-foreground">
            {n !== undefined && <span className="mr-2 font-normal text-muted-foreground">Табл. {n}.</span>}
            {title}
          </h2>
        </div>
        <div className="pt-4">{children}</div>
        {note && <p className="font-display m-0 mt-2 text-[13px] italic text-muted-foreground">{note}</p>}
      </section>
    );
  }
  const box: Record<Exclude<V, 'dossier'>, string> = {
    gos: 'rounded-lg border border-border bg-card',
    dispatch: 'glass rounded-2xl',
    pro: 'rounded-lg border border-border bg-card',
  };
  const head: Record<Exclude<V, 'dossier'>, string> = {
    gos: 'border-b border-border px-5 py-3 text-[16px] font-semibold text-foreground',
    dispatch: 'eyebrow px-5 pt-4 !text-foreground/80',
    pro: 'border-b border-border px-4 py-2.5 text-[13px] font-medium text-foreground',
  };
  return (
    <section className={`flex flex-col ${box[v]} ${className}`}>
      <h2 className={`m-0 ${head[v]}`}>{title}</h2>
      <div className={v === 'pro' ? 'p-4' : 'p-5'}>{children}</div>
      {note && <p className={`m-0 px-5 pb-4 text-[12px] text-muted-foreground ${v === 'pro' ? 'px-4' : ''}`}>{note}</p>}
    </section>
  );
};

const Kpi: React.FC<{ v: V; label: string; value: string | number; hint?: string; alarm?: boolean }> = ({ v, label, value, hint, alarm }) => {
  const color = alarm ? 'var(--danger)' : 'var(--foreground)';
  if (v === 'dossier') {
    return (
      <div className="border-l border-border px-4 py-1 first:border-l-0 first:pl-0">
        <div className="font-display text-[44px] font-bold leading-none" style={{ color }}>{value}</div>
        <div className="mt-2 text-[13px] leading-snug text-muted-foreground">{label}</div>
        {hint && <div className="font-display mt-0.5 text-[12.5px] italic text-muted-foreground">{hint}</div>}
      </div>
    );
  }
  const shell = {
    gos: 'rounded-lg border border-border bg-card px-4 py-3',
    dispatch: 'glass rounded-2xl px-4 py-3',
    pro: 'rounded-lg border border-border bg-card px-4 py-3',
  }[v];
  return (
    <div className={shell}>
      <div className={v === 'dispatch' ? 'eyebrow !text-[10px]' : 'text-[12.5px] text-muted-foreground'}>{label}</div>
      <div
        className={`mt-1.5 leading-none ${v === 'gos' ? 'text-[28px] font-semibold' : 'font-num text-[28px] font-medium'}`}
        style={{ color, textShadow: v === 'dispatch' && alarm ? '0 0 20px var(--danger)' : undefined }}
      >
        {value}
      </div>
      {hint && <div className={`mt-1 text-[12px] text-muted-foreground ${v !== 'gos' ? 'font-num' : ''}`}>{hint}</div>}
    </div>
  );
};

export const DashboardPage: React.FC = () => {
  const incidents = useIncidentStore((s) => s.incidents);
  const v = useStandStore((s) => s.theme);
  const c = useThemeColors();
  const now = useNow(60_000);

  const stats = useMemo(() => executorStats(incidents, now), [incidents, now]);
  const days = useMemo(() => byDay(incidents, 14, now), [incidents, now]);
  const sources = useMemo(() => bySource(incidents), [incidents]);
  const counts = countByStatus(incidents);

  const total = incidents.length;
  const repeatAddr = incidents.filter((i) => getRecidivismCount(i) > 2).length;
  const failed = incidents.filter((i) => isOverdue(i, now) || i.status === 'KNM_ESCALATION').length;
  const closed = counts.CLOSED;
  const closedShare = total ? Math.round((closed / total) * 100) : 0;

  const pieData = STATUS_ORDER.map((s) => ({ name: STATUS_META[s].label, value: counts[s], color: c[STATUS_META[s].cssVar.slice(2) as keyof typeof c] })).filter(
    (d) => d.value > 0,
  );
  const barData = stats.slice(0, 8).map((s) => ({ ...s, short: s.name.replace(/^(УК|МУП|ООО|ТСЖ)\s*/, '').replace(/[«»"]/g, '') }));

  const num = v === 'dossier' ? 'PT Serif, Georgia, serif' : v === 'gos' ? 'Golos Text Variable, sans-serif' : 'JetBrains Mono Variable, monospace';
  const axis = { stroke: c['chart-axis'], fontSize: 12, tickLine: false, axisLine: false, fontFamily: num } as const;
  const tooltip = {
    contentStyle: {
      background: v === 'dispatch' ? c.popover : c.card,
      border: `1px solid ${c.border}`,
      borderRadius: v === 'dossier' ? 0 : 8,
      fontSize: 12.5,
      color: c.foreground,
    },
    labelStyle: { color: c['muted-foreground'] },
    cursor: { fill: v === 'dispatch' || v === 'pro' ? c.accent : c.muted },
  };
  const radius = v === 'dossier' ? 0 : 3;

  const wrap = {
    gos: 'flex w-full flex-col gap-6 p-4 md:p-6',
    dispatch: 'flex w-full flex-col gap-4 p-3 lg:p-4',
    dossier: 'flex w-full flex-col gap-10 px-4 py-8 md:px-4',
    pro: 'flex w-full flex-col gap-4 p-4 lg:p-5',
  }[v];

  return (
    <div className={wrap}>
      {v === 'gos' && (
        <div>
          <h1 className="text-[24px] font-semibold leading-tight text-foreground">Аналитика по исполнителям</h1>
          <p className="mt-1 text-[14px] text-muted-foreground">Обращения и повторные нарушения по организациям, которые содержат площадки</p>
        </div>
      )}
      {v === 'dossier' && (
        <div className="text-center">
          <div className="eyebrow !text-[10.5px]">Раздел второй</div>
          <h1 className="font-display m-0 mt-1 text-[34px] font-bold text-foreground">Исполнители и сроки</h1>
          <p className="font-display m-0 mt-1 text-[16px] italic text-muted-foreground">Как управляющие компании устраняют нарушения на контейнерных площадках</p>
        </div>
      )}

      <div className={v === 'dossier' ? 'grid grid-cols-2 gap-y-6 border-y border-border py-5 md:grid-cols-4' : 'grid grid-cols-2 gap-3 md:grid-cols-4'}>
        <Kpi v={v} label="Всего обращений" value={total} hint={`за 14 дней: ${days.reduce((a, d) => a + d.total, 0)}`} />
        <Kpi v={v} label="Устранено" value={`${closedShare} %`} hint={`${closed} из ${total}`} />
        <Kpi v={v} label="Сорван срок или КНМ" value={failed} alarm={failed > 0} />
        <Kpi v={v} label="Адресов с повтором больше двух раз" value={repeatAddr} alarm={repeatAddr > 0} />
      </div>

      <div className={`grid grid-cols-1 xl:grid-cols-12 ${v === 'dossier' ? 'gap-10' : v === 'gos' ? 'gap-6' : 'gap-4'}`}>
        <Panel v={v} n={1} title="Поступление по дням" note="Последние 14 дней; темнее — уже устранённые." className="xl:col-span-8">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              {v === 'dispatch' ? (
                <AreaChart data={days} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="dsp-area" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={c['chart-1']} stopOpacity={0.45} />
                      <stop offset="100%" stopColor={c['chart-1']} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke={c['chart-grid']} />
                  <XAxis dataKey="label" {...axis} interval={1} />
                  <YAxis allowDecimals={false} {...axis} />
                  <Tooltip {...tooltip} />
                  <Area isAnimationActive={false} type="monotone" dataKey="total" name="Поступило" stroke={c['chart-1']} strokeWidth={2} fill="url(#dsp-area)" />
                  <Area isAnimationActive={false} type="monotone" dataKey="closed" name="Устранено" stroke={c['st-done']} strokeWidth={1.5} fill="transparent" />
                </AreaChart>
              ) : (
                <BarChart data={days} margin={{ top: 8, right: 8, left: -24, bottom: 0 }} barGap={-14}>
                  <CartesianGrid vertical={false} stroke={c['chart-grid']} strokeDasharray={v === 'dossier' ? '2 3' : undefined} />
                  <XAxis dataKey="label" {...axis} interval={1} />
                  <YAxis allowDecimals={false} {...axis} />
                  <Tooltip {...tooltip} />
                  <Bar isAnimationActive={false} dataKey="total" name="Поступило" fill={v === 'dossier' ? c.border : `color-mix(in srgb, ${c['chart-1']} 35%, transparent)`} radius={[radius, radius, 0, 0]} maxBarSize={14} />
                  <Bar isAnimationActive={false} dataKey="closed" name="Устранено" fill={c['chart-1']} radius={[radius, radius, 0, 0]} maxBarSize={14} />
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel v={v} n={2} title="Обращения по стадиям" className="xl:col-span-4">
          <div className="flex items-center gap-4">
            <div className="relative h-44 w-44 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie isAnimationActive={false} data={pieData} cx="50%" cy="50%" innerRadius={52} outerRadius={78} paddingAngle={v === 'dossier' ? 0 : 2} dataKey="value" stroke={v === 'dossier' ? c.card : 'transparent'} strokeWidth={v === 'dossier' ? 2 : 0}>
                    {pieData.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                  </Pie>
                  <Tooltip {...tooltip} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
                <div>
                  <div className={`leading-none text-foreground ${v === 'dossier' ? 'font-display text-[28px] font-bold' : v === 'gos' ? 'text-[26px] font-semibold' : 'font-num text-[24px]'}`}>{total}</div>
                  <div className="mt-1 text-[11px] text-muted-foreground">всего</div>
                </div>
              </div>
            </div>
            <ul className="m-0 flex min-w-0 flex-1 list-none flex-col gap-2 p-0">
              {STATUS_ORDER.map((s) => (
                <li key={s} className="flex items-center gap-2 text-[13px]">
                  <span className={`size-2.5 shrink-0 ${v === 'dossier' ? '' : 'rounded-full'}`} style={{ background: STATUS_META[s].dot }} />
                  <span className="truncate text-foreground">{STATUS_META[s].label}</span>
                  <span className={`ml-auto text-foreground ${v === 'dossier' ? 'font-display font-bold' : v === 'gos' ? 'font-semibold' : 'font-num'}`}>{counts[s]}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        <Panel v={v} n={3} title="Нарушения по исполнителям" note="Сравнение всех нарушений с повторными (больше двух раз за месяц на одном адресе)." className="xl:col-span-7">
          <div className="w-full" style={{ height: Math.max(180, barData.length * 38) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }} barGap={2}>
                <CartesianGrid horizontal={false} stroke={c['chart-grid']} />
                <XAxis type="number" allowDecimals={false} {...axis} />
                <YAxis type="category" dataKey="short" width={134} {...axis} tick={{ fill: c.foreground, fontSize: 12.5 }} />
                <Tooltip {...tooltip} labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ''} />
                <Bar isAnimationActive={false} dataKey="total" name="Всего" fill={c['chart-1']} radius={[0, radius, radius, 0]} maxBarSize={12} />
                <Bar isAnimationActive={false} dataKey="repeat" name="Повторные" fill={c['chart-2']} radius={[0, radius, radius, 0]} maxBarSize={12} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel v={v} n={4} title="Источники обращений" className="xl:col-span-5">
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {sources.map((s) => (
              <li key={s.source} className="text-[13px]">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-foreground">{s.title}</span>
                  <span className={`text-muted-foreground ${v === 'dossier' ? 'font-display' : v === 'gos' ? '' : 'font-num'}`}>
                    {s.count} <span className="text-[11.5px]">· {Math.round((s.count / Math.max(1, total)) * 100)} %</span>
                  </span>
                </div>
                <div className={`mt-1.5 h-1.5 overflow-hidden ${v === 'dossier' ? 'bg-secondary' : 'rounded-full bg-foreground/[0.07]'}`}>
                  <div
                    className={v === 'dossier' ? 'h-full' : 'h-full rounded-full'}
                    style={{
                      width: `${(s.count / Math.max(1, sources[0]?.count ?? 1)) * 100}%`,
                      background: 'var(--chart-1)',
                      boxShadow: v === 'dispatch' ? '0 0 10px var(--chart-1)' : undefined,
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel v={v} n={5} title="Сводная по исполнителям" className="xl:col-span-12">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[13.5px]">
              <thead>
                <tr className={`text-left ${v === 'dossier' || v === 'dispatch' ? 'eyebrow !text-[10.5px]' : 'text-[12.5px] text-muted-foreground'}`}>
                  <th className="py-2 pr-4 font-medium">Исполнитель</th>
                  <th className="py-2 pr-4 text-right font-medium">Всего</th>
                  <th className="py-2 pr-4 text-right font-medium">Повторные</th>
                  <th className="py-2 pr-4 text-right font-medium">Сорван срок / КНМ</th>
                  <th className="py-2 pr-4 text-right font-medium">Устранено</th>
                  <th className="w-[28%] py-2 font-medium">Доля устранённых</th>
                </tr>
              </thead>
              <tbody>
                {stats.map((s) => {
                  const share = s.total ? s.closed / s.total : 0;
                  const numCls = v === 'dossier' ? 'font-display' : v === 'gos' ? '' : 'font-num';
                  return (
                    <tr key={s.name} className={`border-t ${v === 'dossier' ? 'border-dotted border-foreground/25' : 'border-border'}`}>
                      <td className="py-2.5 pr-4 text-foreground">{s.name}</td>
                      <td className={`py-2.5 pr-4 text-right text-foreground ${numCls}`}>{s.total}</td>
                      <td className={`py-2.5 pr-4 text-right ${numCls} ${s.repeat ? 'text-danger' : 'text-muted-foreground'}`}>{s.repeat || '—'}</td>
                      <td className={`py-2.5 pr-4 text-right ${numCls} ${s.overdue ? 'font-semibold text-danger' : 'text-muted-foreground'}`}>{s.overdue || '—'}</td>
                      <td className={`py-2.5 pr-4 text-right text-foreground ${numCls}`}>{s.closed}</td>
                      <td className="py-2.5">
                        <div className="flex items-center gap-2">
                          <div className={`h-1.5 flex-1 overflow-hidden ${v === 'dossier' ? 'bg-secondary' : 'rounded-full bg-foreground/[0.07]'}`}>
                            <div className={`h-full ${v === 'dossier' ? '' : 'rounded-full'}`} style={{ width: `${share * 100}%`, background: 'var(--st-done)' }} />
                          </div>
                          <span className={`w-10 text-right text-[12px] text-muted-foreground ${numCls}`}>{Math.round(share * 100)} %</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
};

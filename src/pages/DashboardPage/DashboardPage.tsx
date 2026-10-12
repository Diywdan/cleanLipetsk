import React, { useMemo } from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { STATUS_META, STATUS_ORDER } from '@/entities/incident/lib/presentation';
import { getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { byDay, bySource, countByStatus, executorStats, isOverdue } from '@/entities/incident/lib/insights';
import { useThemeColors } from '@/shared/theme/themeColors';
import { useNow } from '@/shared/lib/time';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

// Аналитика по исполнителям: стеклянные панели со свечением.

const Panel: React.FC<{ title: string; note?: string; className?: string; children: React.ReactNode }> = ({
  title,
  note,
  className = '',
  children,
}) => {
  return (
    <section className={`glass flex flex-col rounded-2xl ${className}`}>
      <h2 className="eyebrow m-0 px-5 pt-4 !text-foreground/80">{title}</h2>
      <div className="p-5">{children}</div>
      {note && <p className="m-0 px-5 pb-4 text-[12px] text-muted-foreground">{note}</p>}
    </section>
  );
};

const Kpi: React.FC<{ label: string; value: string | number; hint?: string; alarm?: boolean }> = ({ label, value, hint, alarm }) => {
  const color = alarm ? 'var(--danger)' : 'var(--foreground)';
  return (
    <div className="glass rounded-2xl px-4 py-3">
      <div className="eyebrow !text-[10px]">{label}</div>
      <div
        className="font-num mt-1.5 text-[28px] font-medium leading-none"
        style={{ color, textShadow: alarm ? '0 0 20px var(--danger)' : undefined }}
      >
        {value}
      </div>
      {hint && <div className="font-num mt-1 text-[12px] text-muted-foreground">{hint}</div>}
    </div>
  );
};

export const DashboardPage: React.FC = () => {
  const incidents = useIncidentStore((s) => s.incidents);
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

  const num = 'JetBrains Mono Variable, monospace';
  const axis = { stroke: c['chart-axis'], fontSize: 12, tickLine: false, axisLine: false, fontFamily: num } as const;
  const tooltip = {
    contentStyle: {
      background: c.popover,
      border: `1px solid ${c.border}`,
      borderRadius: 8,
      fontSize: 12.5,
      color: c.foreground,
    },
    labelStyle: { color: c['muted-foreground'] },
    cursor: { fill: c.accent },
  };
  const radius = 3;

  return (
    <div className="flex w-full flex-col gap-4 p-3 lg:p-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Всего обращений" value={total} hint={`за 14 дней: ${days.reduce((a, d) => a + d.total, 0)}`} />
        <Kpi label="Устранено" value={`${closedShare} %`} hint={`${closed} из ${total}`} />
        <Kpi label="Сорван срок или КНМ" value={failed} alarm={failed > 0} />
        <Kpi label="Адресов с повтором больше двух раз" value={repeatAddr} alarm={repeatAddr > 0} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <Panel title="Поступление по дням" note="Последние 14 дней; темнее — уже устранённые." className="xl:col-span-8">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
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
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Обращения по стадиям" className="xl:col-span-4">
          <div className="flex items-center gap-4">
            <div className="relative h-44 w-44 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie isAnimationActive={false} data={pieData} cx="50%" cy="50%" innerRadius={52} outerRadius={78} paddingAngle={2} dataKey="value" stroke="transparent" strokeWidth={0}>
                    {pieData.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                  </Pie>
                  <Tooltip {...tooltip} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
                <div>
                  <div className="font-num text-[24px] leading-none text-foreground">{total}</div>
                  <div className="mt-1 text-[11px] text-muted-foreground">всего</div>
                </div>
              </div>
            </div>
            <ul className="m-0 flex min-w-0 flex-1 list-none flex-col gap-2 p-0">
              {STATUS_ORDER.map((s) => (
                <li key={s} className="flex items-center gap-2 text-[13px]">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: STATUS_META[s].dot }} />
                  <span className="truncate text-foreground">{STATUS_META[s].label}</span>
                  <span className="font-num ml-auto text-foreground">{counts[s]}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        <Panel title="Нарушения по исполнителям" note="Сравнение всех нарушений с повторными (больше двух раз за месяц на одном адресе)." className="xl:col-span-7">
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

        <Panel title="Источники обращений" className="xl:col-span-5">
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {sources.map((s) => (
              <li key={s.source} className="text-[13px]">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-foreground">{s.title}</span>
                  <span className="font-num text-muted-foreground">
                    {s.count} <span className="text-[11.5px]">· {Math.round((s.count / Math.max(1, total)) * 100)} %</span>
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-foreground/[0.07]">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(s.count / Math.max(1, sources[0]?.count ?? 1)) * 100}%`,
                      background: 'var(--chart-1)',
                      boxShadow: '0 0 10px var(--chart-1)',
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Сводная по исполнителям" className="xl:col-span-12">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[13.5px]">
              <thead>
                <tr className="eyebrow text-left !text-[10.5px]">
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
                  const numCls = 'font-num';
                  return (
                    <tr key={s.name} className="border-t border-border">
                      <td className="py-2.5 pr-4 text-foreground">{s.name}</td>
                      <td className={`py-2.5 pr-4 text-right text-foreground ${numCls}`}>{s.total}</td>
                      <td className={`py-2.5 pr-4 text-right ${numCls} ${s.repeat ? 'text-danger' : 'text-muted-foreground'}`}>{s.repeat || '—'}</td>
                      <td className={`py-2.5 pr-4 text-right ${numCls} ${s.overdue ? 'font-semibold text-danger' : 'text-muted-foreground'}`}>{s.overdue || '—'}</td>
                      <td className={`py-2.5 pr-4 text-right text-foreground ${numCls}`}>{s.closed}</td>
                      <td className="py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-foreground/[0.07]">
                            <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: 'var(--st-done)' }} />
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

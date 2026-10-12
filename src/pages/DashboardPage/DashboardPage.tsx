import React from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { getPrimaryOrganizationName, getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { STATUS_META, STATUS_ORDER, typoQuotes } from '@/entities/incident/lib/presentation';
import { StatTile } from '@/shared/components/stat-tile/StatTile';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

const AXIS = { stroke: '#5C6B7A', fontSize: 13, tickLine: false } as const;
const TOOLTIP = {
  contentStyle: { backgroundColor: '#fff', border: '1px solid #DCE3EB', borderRadius: 8, fontSize: 13 },
};

const Panel: React.FC<{ title: string; className?: string; children: React.ReactNode }> = ({ title, className = '', children }) => (
  <section className={`flex flex-col rounded-lg border border-border bg-card ${className}`}>
    <h2 className="border-b border-border px-5 py-3 text-[16px] font-semibold text-foreground">{title}</h2>
    <div className="p-5">{children}</div>
  </section>
);

export const DashboardPage: React.FC = () => {
  const { incidents } = useIncidentStore();

  // Статистика по основному ответственному (тот, кто содержит площадку)
  const ukStatsMap: Record<string, { name: string; total: number; recidivism: number }> = {};

  incidents.forEach((inc) => {
    const ukName = typoQuotes(getPrimaryOrganizationName(inc));
    if (!ukStatsMap[ukName]) {
      ukStatsMap[ukName] = { name: ukName, total: 0, recidivism: 0 };
    }
    ukStatsMap[ukName].total += 1;
    ukStatsMap[ukName].recidivism += getRecidivismCount(inc) > 1 ? 1 : 0;
  });

  const chartData = Object.values(ukStatsMap).sort((a, b) => b.total - a.total);

  const statusCounts = incidents.reduce((acc: Record<string, number>, inc) => {
    acc[inc.status] = (acc[inc.status] || 0) + 1;
    return acc;
  }, {});

  const pieData = STATUS_ORDER.map((status) => ({
    name: STATUS_META[status].label,
    value: statusCounts[status] || 0,
    color: STATUS_META[status].dot,
  })).filter((item) => item.value > 0);

  const critical = incidents.filter((i) => getRecidivismCount(i) > 2).length;
  const done = incidents.filter((i) => i.status === 'VERIFICATION' || i.status === 'CLOSED').length;

  return (
    <div className="flex w-full flex-col gap-6 p-4 md:p-6">
      <div>
        <h1 className="text-[24px] font-semibold leading-tight text-foreground">Аналитика по исполнителям</h1>
        <p className="mt-1 text-[14px] text-muted-foreground">
          Обращения и повторные нарушения по организациям, которые содержат площадки
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <StatTile label="Всего обращений" value={incidents.length} />
        <StatTile label="Адресов с нарушением больше двух раз за месяц" value={critical} tone="danger" />
        <StatTile label="На проверке или закрыто" value={done} />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <Panel title="Нарушения по управляющим компаниям" className="xl:col-span-7">
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#EEF3F8" />
                <XAxis dataKey="name" {...AXIS} />
                <YAxis allowDecimals={false} {...AXIS} />
                <Tooltip {...TOOLTIP} cursor={{ fill: '#F5F7FA' }} />
                <Legend wrapperStyle={{ fontSize: 13, paddingTop: 12 }} />
                <Bar dataKey="total" name="Всего нарушений" fill="#0D4CD3" radius={[3, 3, 0, 0]} maxBarSize={48} />
                <Bar dataKey="recidivism" name="Из них повторные" fill="#EE3F58" radius={[3, 3, 0, 0]} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Обращения по стадиям" className="xl:col-span-5">
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <div className="h-64 w-full sm:w-1/2">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={62} outerRadius={96} paddingAngle={2} dataKey="value" stroke="#fff">
                    {pieData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip {...TOOLTIP} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="flex w-full flex-col gap-2 sm:w-1/2">
              {pieData.map((item) => (
                <li key={item.name} className="flex items-center gap-2 text-[14px]">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                  <span className="text-foreground">{item.name}</span>
                  <span className="ml-auto font-semibold text-foreground">{item.value}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      </div>
    </div>
  );
};

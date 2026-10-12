import React from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { getPrimaryOrganizationName, getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { ShieldAlert, TrendingUp, CheckCircle, BarChart3 } from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const { incidents } = useIncidentStore();

  // Собираем статистику по УК из живого Zustand-стора
  const ukStatsMap: Record<string, { name: string; total: number; recidivism: number }> = {};

  incidents.forEach((inc) => {
    const ukName = getPrimaryOrganizationName(inc);
    if (!ukStatsMap[ukName]) {
      ukStatsMap[ukName] = { name: ukName, total: 0, recidivism: 0 };
    }
    ukStatsMap[ukName].total += 1;
    ukStatsMap[ukName].recidivism += getRecidivismCount(inc) > 1 ? 1 : 0;
  });

  const chartData = Object.values(ukStatsMap);

  // Статистика по статусам для круговой диаграммы
  const statusCounts = incidents.reduce((acc: Record<string, number>, inc) => {
    acc[inc.status] = (acc[inc.status] || 0) + 1;
    return acc;
  }, {});

  const pieData = [
    { name: 'Новые инциденты', value: statusCounts['NEW'] || 0, color: '#475569' },
    { name: 'В работе у УК', value: statusCounts['IN_PROGRESS'] || 0, color: '#6366f1' },
    { name: 'На верификации', value: statusCounts['VERIFICATION'] || 0, color: '#ec4899' },
    { name: 'Эскалация в ГЖИ', value: statusCounts['KNM_ESCALATION'] || 0, color: '#be123c' },
  ].filter(item => item.value > 0); // Показываем только те, которые есть

  return (
    <div className="p-6 bg-slate-50 min-h-screen text-slate-900 flex flex-col gap-6 w-full">
      {/* Шапка дашборда для руководства Липецка */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <div>
          <h2 className="text-xl font-black text-slate-800 tracking-tight flex items-center gap-2">
            <BarChart3 className="text-blue-600 w-6 h-6" /> Сводный аналитический дашборд ДРТ Липецка
          </h2>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Оперативная витрина эффективности Управляющих компаний по контролю благоустройства ТКО
          </p>
        </div>
      </div>

      {/* БЛОК КАРТОЧЕК ВЕРХНЕГО УРОВНЯ (KPI) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full">
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex items-center gap-4">
          <div className="p-3 bg-blue-50 rounded-lg text-blue-600"><ShieldAlert className="w-6 h-6" /></div>
          <div>
            <span className="block text-xs text-slate-400 font-bold uppercase">Всего инцидентов в системе</span>
            <span className="text-2xl font-black text-slate-700">{incidents.length}</span>
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex items-center gap-4">
          <div className="p-3 bg-rose-50 rounded-lg text-rose-600"><TrendingUp className="w-6 h-6" /></div>
          <div>
            <span className="block text-xs text-slate-400 font-bold uppercase">Критические рецидивы УК</span>
            <span className="text-2xl font-black text-rose-600">
              {incidents.filter(i => getRecidivismCount(i) > 2).length}
            </span>
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex items-center gap-4">
          <div className="p-3 bg-emerald-50 rounded-lg text-emerald-600"><CheckCircle className="w-6 h-6" /></div>
          <div>
            <span className="block text-xs text-slate-400 font-bold uppercase">Дел на верификации / Закрыто</span>
            <span className="text-2xl font-black text-emerald-600">
              {incidents.filter(i => i.status === 'VERIFICATION' || i.status === 'CLOSED').length}
            </span>
          </div>
        </div>
      </div>

      {/* СЕТКА ДИАГРАММ */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 w-full">
        {/* График 1: Столбчатая диаграмма нарушений по УК (7 колонок) */}
        <div className="xl:col-span-7 bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col gap-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Антирейтинг Управляющих компаний (Количество инцидентов)
          </h3>
          <div className="w-full h-75">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={10} tickLine={false} />
                <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }} />
                <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />
                <Bar dataKey="total" name="Всего нарушений" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="recidivism" name="Из них повторные" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* График 2: Круговая диаграмма долей статусов дел (5 колонок) */}
        <div className="xl:col-span-5 bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col gap-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Разрез оперативных дел по стадиям контроля
          </h3>
          <div className="w-full h-75 flex items-center justify-center relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={90} paddingAngle={4} dataKey="value">
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }} />
              </PieChart>
            </ResponsiveContainer>
            {/* Кастомная легенда списком справа */}
            <div className="absolute right-2 bottom-2 flex flex-col gap-1 text-[11px] font-semibold text-slate-600">
              {pieData.map((item, idx) => (
                <div key={idx} className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                  <span>{item.name}: <b className="text-slate-800">{item.value}</b></span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

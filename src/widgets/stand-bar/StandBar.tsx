import React from 'react';
import { useAuthStore } from '@/entities/user/model/authStore';
import type { UserRole } from '@/entities/user/types';
import { THEMES, useStandStore, type DatasetId } from '@/shared/theme/standStore';

// Полоса демонстрационного стенда — одна на все темы.
// Переключает направление дизайна, набор данных и роль без входа в систему.
const ROLES: { role: UserRole; title: string }[] = [
  { role: 'INSPECTOR', title: 'Инспектор' },
  { role: 'UK', title: 'Мастер УК' },
  { role: 'ADMIN', title: 'Руководство' },
];

const DATASETS: { id: DatasetId; title: string }[] = [
  { id: 'demo', title: 'Расширенные' },
  { id: 'mock', title: 'Макет (4)' },
];

const Segmented: React.FC<{
  label: string;
  items: { id: string; title: string; hint?: string }[];
  value: string;
  onChange: (id: string) => void;
}> = ({ label, items, value, onChange }) => (
  <div className="flex min-w-0 items-center gap-2">
    <span className="hidden text-white/55 lg:inline">{label}</span>
    {/* Узкий экран — выпадающий список, широкий — переключатель */}
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
      className="min-w-0 cursor-pointer rounded-md border-0 bg-white/[0.09] px-1.5 py-1 text-[12.5px] text-white outline-none md:hidden [&>option]:text-black"
    >
      {items.map((item) => (
        <option key={item.id} value={item.id}>{item.title}</option>
      ))}
    </select>
    <div className="hidden rounded-md bg-white/[0.07] p-0.5 md:flex" role="radiogroup" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="radio"
          aria-checked={value === item.id}
          title={item.hint}
          onClick={() => onChange(item.id)}
          className={`cursor-pointer whitespace-nowrap rounded px-2.5 py-0.5 transition-colors ${
            value === item.id ? 'bg-white text-[#0B1220]' : 'text-white/75 hover:bg-white/10 hover:text-white'
          }`}
        >
          {item.title}
        </button>
      ))}
    </div>
  </div>
);

export const StandBar: React.FC = () => {
  const { theme, setTheme, dataset, setDataset } = useStandStore();
  const { currentUser, switchDevRole } = useAuthStore();

  const setRole = (role: string) => {
    if (role === 'UK') switchDevRole('UK', 'DRT', 'УК "Левобережная"');
    else switchDevRole(role as UserRole, 'DRT');
  };

  return (
    <div
      className="relative z-50 flex shrink-0 items-center gap-x-3 md:flex-wrap md:gap-x-5 gap-y-1.5 bg-[#0B1220] px-4 py-1.5 text-[12.5px] text-white/80 md:px-5"
      style={{ fontFamily: "'Golos Text Variable', sans-serif" }}
    >
      <span className="flex items-center gap-2">
        <span className="size-1.5 rounded-full bg-[#F5B83D]" />
        <span className="hidden sm:inline">Демонстрационный стенд · данные условные</span>
        <span className="hidden min-[420px]:inline sm:hidden">Стенд</span>
      </span>
      <div className="ml-auto flex min-w-0 items-center gap-x-2 md:flex-wrap md:gap-x-5 md:gap-y-1.5">
        <Segmented label="Дизайн" items={THEMES} value={theme} onChange={(id) => setTheme(id as typeof theme)} />
        <div className="hidden sm:block">
          <Segmented label="Данные" items={DATASETS} value={dataset} onChange={(id) => setDataset(id as DatasetId)} />
        </div>
        <Segmented
          label="Роль"
          items={ROLES.map((r) => ({ id: r.role, title: r.title }))}
          value={currentUser?.role ?? 'INSPECTOR'}
          onChange={setRole}
        />
      </div>
    </div>
  );
};

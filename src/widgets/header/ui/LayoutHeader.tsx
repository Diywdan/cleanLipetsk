import React from 'react';
import { useAuthStore } from '@/entities/user/model/authStore';
import type { UserRole } from '@/entities/user/types';
import { Landmark } from 'lucide-react';

export type AppTab = 'map_view' | 'analytics';

const ROLE_TITLE: Record<UserRole, string> = {
  INSPECTOR: 'Инспектор ДРТ',
  UK: 'Мастер управляющей компании',
  ADMIN: 'Руководство',
};

const TABS: { id: AppTab; title: string; short: string }[] = [
  { id: 'map_view', title: 'Карта и реестр', short: 'Карта' },
  { id: 'analytics', title: 'Аналитика по исполнителям', short: 'Аналитика' },
];

interface TProps {
  activeTab: AppTab;
  onTabChange: (tab: AppTab) => void;
}

function initials(name: string): string {
  return name
    .replace(/\(.*?\)/g, '')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();
}

export const LayoutHeader: React.FC<TProps> = ({ activeTab, onTabChange }) => {
  const currentUser = useAuthStore((s) => s.currentUser);

  // Роли и тема переключаются в полосе стенда (StandBar) — здесь только шапка
  return (
    <div className="shrink-0">
      <header className="flex h-16 items-stretch gap-4 border-b border-border bg-card px-4 md:gap-8 md:px-6">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Landmark className="size-5" />
          </div>
          <div className="hidden leading-tight sm:block">
            <div className="text-[17px] font-semibold text-foreground">Чистый Липецк</div>
            <div className="hidden text-[13px] text-muted-foreground lg:block">
              Контроль содержания контейнерных площадок
            </div>
          </div>
        </div>

        <nav className="flex items-stretch gap-4 md:gap-6" aria-label="Разделы">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              className={`-mb-px cursor-pointer whitespace-nowrap border-b-2 text-[15px] transition-colors ${
                activeTab === tab.id
                  ? 'border-primary font-medium text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <span className="md:hidden">{tab.short}</span>
              <span className="hidden md:inline">{tab.title}</span>
            </button>
          ))}
        </nav>

        {currentUser && (
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right leading-tight lg:block">
              <div className="text-[14px] font-medium text-foreground">{currentUser.name}</div>
              <div className="text-[13px] text-muted-foreground">
                {ROLE_TITLE[currentUser.role]}
                {currentUser.organizationName && ` · ${currentUser.organizationName}`}
              </div>
            </div>
            <div className="grid size-9 place-items-center rounded-full bg-secondary text-[13px] font-semibold text-secondary-foreground">
              {initials(currentUser.name)}
            </div>
          </div>
        )}
      </header>
    </div>
  );
};

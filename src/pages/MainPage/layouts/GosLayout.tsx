import React from 'react';
import { UniversalIncidentCard } from '@/entities/incident/ui/UniversalIncidentCard';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useAuthStore } from '@/entities/user/model/authStore';
import { summarizeIncidents, todayLabel } from '@/entities/incident/lib/summary';
import { useNow } from '@/shared/lib/time';
import { StatTile } from '@/shared/components/stat-tile/StatTile';
import { MapRadar } from '@/widgets/map-radar';
import { IncidentSmartTable } from '@/widgets/incident-table';
import { LayoutHeader } from '@/widgets/header';
import { DashboardPage } from '../../DashboardPage/DashboardPage';
import { APP_TABS, useUrlState, type AppTab } from './shared';

// Базовая тема — первый вариант в палитре Госуслуг: шапка, сводка, карта и реестр слева,
// карточка обращения справа.
export const GosLayout: React.FC = () => {
  const incidents = useIncidentStore((s) => s.incidents);
  const currentUser = useAuthStore((s) => s.currentUser);
  const [tab, setTab] = useUrlState<AppTab>('map_view', APP_TABS);
  const now = useNow();
  const summary = summarizeIncidents(incidents, now);

  return (
    <div className="flex h-full flex-col">
      <LayoutHeader activeTab={tab} onTabChange={setTab} />
      <div className="min-h-0 w-full flex-1 overflow-y-auto">
        {tab === 'analytics' ? (
          <div className="mx-auto w-full max-w-[1600px]">
            <DashboardPage />
          </div>
        ) : (
          <main className="mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-6 p-4 md:p-6 xl:h-full xl:grid-cols-12">
            <section className="flex min-h-0 flex-col gap-6 xl:col-span-7 xl:overflow-y-auto xl:pr-1">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <h1 className="text-[24px] font-semibold leading-tight text-foreground">Оперативный контроль</h1>
                <span className="text-[14px] text-muted-foreground">Липецк · на {todayLabel()}</span>
              </div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <StatTile label="Открытых обращений" value={summary.open} />
                <StatTile label="Новые, ждут проверки" value={summary.fresh} />
                <StatTile label="Срок устранения истёк" value={summary.overdue} tone="danger" />
                <StatTile label="Передано на КНМ" value={summary.knm} tone="danger" />
              </div>
              <MapRadar />
              <IncidentSmartTable />
            </section>
            <section className="flex min-h-0 flex-col xl:col-span-5">
              {currentUser && <UniversalIncidentCard userRole={currentUser.role} />}
            </section>
          </main>
        )}
      </div>
    </div>
  );
};

import React, { useState } from "react";
import { UniversalIncidentCard } from "@/entities/incident/ui/UniversalIncidentCard";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { MapRadar } from "@/widgets/map-radar";
import { IncidentSmartTable } from "@/widgets/incident-table";
import { useAuthStore } from "@/entities/user/model/authStore";
import { LayoutHeader } from "@/widgets/header";
import type { AppTab } from "@/widgets/header/ui/LayoutHeader";
import { summarizeIncidents, todayLabel } from "@/entities/incident/lib/summary";
import { StatTile } from "@/shared/components/stat-tile/StatTile";
import { DashboardPage } from "../DashboardPage/DashboardPage";

export const MainPage: React.FC = () => {
  const incidents = useIncidentStore((state) => state.incidents);
  const currentUser = useAuthStore((state) => state.currentUser);
  const [activeTab, setActiveTab] = useState<AppTab>("map_view");

  // Сводка считается по тем же данным, что в реестре
  const summary = summarizeIncidents(incidents);
  const today = todayLabel();

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background">
      <LayoutHeader activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="min-h-0 w-full flex-1 overflow-y-auto">
        {activeTab === "analytics" ? (
          <div className="mx-auto w-full max-w-[1600px]">
            <DashboardPage />
          </div>
        ) : (
          <main className="mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-6 p-4 md:p-6 xl:h-full xl:grid-cols-12">
            <section className="flex min-h-0 flex-col gap-6 xl:col-span-7 xl:overflow-y-auto xl:pr-1">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <h1 className="text-[24px] font-semibold leading-tight text-foreground">
                  Оперативный контроль
                </h1>
                <span className="text-[14px] text-muted-foreground">Липецк · на {today}</span>
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

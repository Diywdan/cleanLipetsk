import React, { useState } from "react";
import { UniversalIncidentCard } from "@/entities/incident/ui/UniversalIncidentCard";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { MapRadar } from "@/widgets/map-radar";
import { Eye, Map, BarChart3 } from "lucide-react"; 
import { IncidentSmartTable } from "@/widgets/incident-table";
import { useAuthStore } from "@/entities/user/model/authStore";
import { DashboardPage } from "../DashboardPage/DashboardPage"; 

export const MainPage: React.FC = () => {
  const selectedIncident = useIncidentStore((state) => state.selectedIncident);
  const currentUser = useAuthStore((state) => state.currentUser);
  
  // 🎛️ РЕАКТИВНЫЙ СТEЙТ ПЕРЕКЛЮЧЕНИЯ ЭКРАНОВ: ГИС-Вид по умолчанию
  const [activeTab, setActiveTab] = useState<'map_view' | 'analytics'>('map_view');

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 overflow-hidden">
      
      {/* 1. СУВЕРЕННАЯ ВЕДОМСТВЕННАЯ ШАПКА ДЛЯ УПРАВЛЕНИЯ ЭКРАНАМИ */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between shadow-xs shrink-0 w-full">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600 px-2 py-1 rounded text-white font-black text-xs tracking-wider">
            ДРТ
          </div>
          <div>
            <h1 className="text-xs font-black text-slate-800 tracking-tight">«ЧИСТЫЙ ЛИПЕЦК»</h1>
            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider">Система контроля благоустройства</p>
          </div>
        </div>

        {/* ПЕРЕКЛЮЧАТЕЛЬ РЕЖИМОВ (ЗАДАЧА №16) */}
        <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200 gap-1">
          <button
            onClick={() => setActiveTab('map_view')}
            className={`text-xs px-3 py-1.5 rounded-md font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'map_view'
                ? 'bg-white text-blue-600 shadow-xs'
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50/50'
            }`}
          >
            <Map className="w-3.5 h-3.5" /> ГИС-Радар и Реестр
          </button>
          <button
            onClick={() => setActiveTab('analytics')}
            className={`text-xs px-3 py-1.5 rounded-md font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'analytics'
                ? 'bg-white text-blue-600 shadow-xs'
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50/50'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" /> Аналитика УК (SLA)
          </button>
        </div>

        <div className="text-[11px] font-bold text-slate-500 bg-slate-50 px-2.5 py-1 rounded border border-slate-200 uppercase tracking-wide">
          👤 {currentUser ? `Роль: ${currentUser.role}` : 'Авторизация...'}
        </div>
      </header>

      {/* 2. ДИНАМИЧЕСКИЙ КОНТЕНТ СТРАНИЦЫ */}
      <div className="flex-1 overflow-y-auto w-full">
        {activeTab === 'analytics' ? (
          /* ЭКРАН А: Панель графиков и диаграмм (Задача №16) */
          <div className="max-w-[1600px] w-full mx-auto">
            <DashboardPage />
          </div>
        ) : (
          /* ЭКРАН Б: Твой исходный, идеальный рабочий контур ГИС-мониторинга */
          <main className="grid grid-cols-1 xl:grid-cols-12 gap-6 p-6 max-w-[1600px] w-full mx-auto h-full">
            {/* ЛЕВАЯ СЕКЦИЯ: ГИС-РАДАР И ОПЕРАТИВНАЯ ТАБЛИЦА (7 из 12 колонок) */}
            <section className="xl:col-span-7 flex flex-col gap-6 h-full overflow-y-auto pr-1">
              <div className="flex flex-col gap-3">
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <Eye className="w-3.5 h-3.5" /> Карта мониторинга нарушений благоустройства
                </h2>
                <MapRadar />
              </div>

              <div className="flex flex-col gap-3">
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  Оперативный реестр текущих дел контроля SLA
                </h2>
                <IncidentSmartTable />
              </div>
            </section>

            {/* ПРАВАЯ СЕКЦИЯ: ЕДИНOЕ ОКНО КАРТОЧКИ ДЕЛА (5 из 12 колонок) */}
            <section className="xl:col-span-5 flex flex-col gap-3 h-full">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                {selectedIncident
                  ? "Единое окно детального просмотра инцидента"
                  : "Панель действий"}
              </h2>
              {currentUser && <UniversalIncidentCard userRole={currentUser.role}/>}
            </section>
          </main>
        )}
      </div>

    </div>
  );
};

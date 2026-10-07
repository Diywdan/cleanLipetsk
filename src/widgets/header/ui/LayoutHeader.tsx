import React from 'react';
import { useAuthStore } from '@/entities/user/model/authStore';
import { ShieldCheck, UserSquare2 } from 'lucide-react';

export const LayoutHeader: React.FC = () => {
  const { currentUser, switchDevRole } = useAuthStore();

  return (
    <>
      {/* 🏙️ ГЛАВНАЯ СИСТЕМНАЯ ШАПКА */}
      <header className="bg-slate-900 text-white px-6 py-4 flex items-center justify-between shadow-md border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-600 rounded-lg shadow-inner font-black tracking-wider text-sm">ЦК</div>
          <div>
            <h1 className="text-sm font-bold tracking-tight">Цифровой контур контроля благоустройства</h1>
            <p className="text-[10px] text-slate-400 font-medium">Система ИИ-видеоаналитики объектов ТКО • г. Липецк</p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 bg-slate-800 border border-slate-700/60 px-3 py-1.5 rounded-lg text-xs">
          <UserSquare2 className="w-4 h-4 text-blue-400" />
          <div>
            <span className="block font-semibold text-slate-200">{currentUser?.name}</span>
            <span className="block text-[10px] text-slate-400 font-medium uppercase tracking-wide">
              Роль: {currentUser?.role} {currentUser?.organizationName && `| ${currentUser.organizationName}`}
            </span>
          </div>
        </div>
      </header>

      {/* 🛠️ ПАНЕЛЬ РАЗРАБОТЧИКА (DEV TOOLBAR) */}
      <div className="bg-blue-50 border-b border-blue-100 px-6 py-2 flex flex-wrap items-center gap-4 text-xs font-semibold text-blue-900 shadow-xs">
        <div className="flex items-center gap-1 text-blue-700">
          <ShieldCheck className="w-4 h-4" />
          <span>Панель хакинга ролей (DEV-мод):</span>
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={() => switchDevRole('INSPECTOR', 'DRT')}
            className={`px-2.5 py-1 rounded-md border font-bold transition-all ${currentUser?.role === 'INSPECTOR' ? 'bg-blue-700 text-white border-transparent shadow-xs' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
          >
            👤 Войти как Инспектор ДРТ
          </button>
          <button
            onClick={() => switchDevRole('UK', 'DRT', 'УК "Левобережная"')}
            className={`px-2.5 py-1 rounded-md border font-bold transition-all ${currentUser?.role === 'UK' ? 'bg-amber-600 text-white border-transparent shadow-xs' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
          >
            🚜 Войти как Мастер УК
          </button>
          <button
            onClick={() => switchDevRole('ADMIN', 'DRT')}
            className={`px-2.5 py-1 rounded-md border font-bold transition-all ${currentUser?.role === 'ADMIN' ? 'bg-purple-700 text-white border-transparent shadow-xs' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
          >
            📊 Войти как Руководство (ЦУР)
          </button>
        </div>
      </div>
    </>
  );
};

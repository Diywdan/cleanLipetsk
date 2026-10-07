import React from 'react';
import { Bot, User, ShieldAlert, Cpu } from 'lucide-react';
import type { IHistoryEvent } from '../types';

interface TProps {
  history?: IHistoryEvent[];
}

export const IncidentAuditLog: React.FC<TProps> = ({ history = [] }) => {
  if (history.length === 0) {
    return <p className="text-xs text-slate-400 italic">История операций пуста</p>;
  }

  // Функция для подбора правильной иконки на основе автора события
  const getEventIcon = (type: 'AI' | 'INSPECTOR' | 'UK' | 'SYSTEM') => {
    switch (type) {
      case 'AI':
        return <Bot className="w-3.5 h-3.5 text-blue-600" />;
      case 'INSPECTOR':
        return <User className="w-3.5 h-3.5 text-purple-600" />;
      case 'UK':
        return <Cpu className="w-3.5 h-3.5 text-amber-600" />;
      case 'SYSTEM':
        return <ShieldAlert className="w-3.5 h-3.5 text-slate-500" />;
    }
  };

  return (
    <div className="mt-4">
      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">
        Ведомственный аудит-лог дела (История)
      </h4>
      <div className="relative pl-4 border-l border-slate-200 space-y-4">
        {history.map((event) => (
          <div key={event.id} className="relative group">
            {/* Круглая точка-иконка на вертикальной оси таймлайна */}
            <div className="absolute -left-6.25 top-0.5 bg-white border border-slate-200 rounded-full w-5 h-5 flex items-center justify-center shadow-xs">
              {getEventIcon(event.type)}
            </div>
            
            {/* Текстовый блок события */}
            <div className="text-xs">
              <div className="flex items-center justify-between gap-4 mb-0.5">
                <span className="font-bold text-slate-800">{event.title}</span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {new Date(event.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              <p className="text-slate-500 font-medium leading-relaxed">{event.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

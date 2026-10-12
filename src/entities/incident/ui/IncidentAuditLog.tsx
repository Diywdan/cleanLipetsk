import React from 'react';
import { Bot, User, Building2, Settings } from 'lucide-react';
import type { IHistoryEvent } from '../types';

interface TProps {
  history?: IHistoryEvent[];
}

const AUTHOR: Record<IHistoryEvent['type'], { title: string; icon: React.ReactNode }> = {
  AI: { title: 'ИИ', icon: <Bot className="size-3.5" /> },
  INSPECTOR: { title: 'Инспектор', icon: <User className="size-3.5" /> },
  UK: { title: 'УК', icon: <Building2 className="size-3.5" /> },
  SYSTEM: { title: 'Система', icon: <Settings className="size-3.5" /> },
};

export const IncidentAuditLog: React.FC<TProps> = ({ history = [] }) => {
  if (history.length === 0) {
    return <p className="mt-4 text-[14px] text-muted-foreground">Действий по делу пока нет.</p>;
  }

  return (
    <div className="mt-5">
      <h4 className="mb-3 text-[14px] font-medium text-foreground">История действий</h4>
      <ol className="relative ml-3 space-y-4 border-l border-border">
        {history.map((event) => (
          <li key={event.id} className="relative pl-6">
            <span
              className="absolute -left-3 top-0 grid size-6 place-items-center rounded-full border border-border bg-card text-muted-foreground"
              title={AUTHOR[event.type].title}
            >
              {AUTHOR[event.type].icon}
            </span>
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-[14px] font-medium text-foreground">{event.title}</span>
              <time className="shrink-0 text-[13px] text-muted-foreground" dateTime={event.timestamp}>
                {new Date(event.timestamp).toLocaleString('ru-RU', {
                  day: '2-digit',
                  month: '2-digit',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </time>
            </div>
            <p className="mt-0.5 text-[14px] text-muted-foreground">{event.description}</p>
          </li>
        ))}
      </ol>
    </div>
  );
};

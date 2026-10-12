import React from 'react';

interface TProps {
  label: string;
  value: number | string;
  hint?: string;
  // danger красит число, только когда оно не ноль: ноль просрочек — хорошая новость
  tone?: 'default' | 'danger';
}

export const StatTile: React.FC<TProps> = ({ label, value, hint, tone = 'default' }) => {
  const alarm = tone === 'danger' && Number(value) > 0;
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div className="text-[13px] leading-snug text-muted-foreground">{label}</div>
      <div
        className={`mt-1 text-[28px] font-semibold leading-none ${alarm ? 'text-danger' : 'text-foreground'}`}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-[12px] text-muted-foreground">{hint}</div>}
    </div>
  );
};

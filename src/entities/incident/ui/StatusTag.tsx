import React from 'react';
import type { IncidentStatus } from '../types';
import { STATUS_META } from '../lib/presentation';

export const StatusTag: React.FC<{ status: IncidentStatus; className?: string }> = ({
  status,
  className = '',
}) => {
  const meta = STATUS_META[status];
  if (!meta) return null;
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-[13px] font-medium ${className}`}
      style={{ color: meta.text, backgroundColor: meta.bg }}
    >
      <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: meta.dot }} />
      {meta.label}
    </span>
  );
};

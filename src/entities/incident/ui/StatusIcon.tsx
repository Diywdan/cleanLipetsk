import React from 'react';
import type { IncidentStatus } from '../types';
import { STATUS_META } from '../lib/presentation';

// Значок стадии в духе трекеров задач: по форме видно, насколько дело продвинулось.
// Новое — пунктирный круг, в работе — наполовину залит, проверка — на три четверти,
// устранено — галочка, КНМ — восклицательный знак.
export const StatusIcon: React.FC<{ status: IncidentStatus; size?: number; className?: string }> = ({
  status,
  size = 14,
  className,
}) => {
  const color = STATUS_META[status].dot;
  const common = { width: size, height: size, viewBox: '0 0 14 14', className, 'aria-hidden': true } as const;

  switch (status) {
    case 'NEW':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke={color} strokeWidth="1.5" strokeDasharray="2.2 1.8" />
        </svg>
      );
    case 'IN_PROGRESS':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke={color} strokeWidth="1.5" />
          <path d="M7 3.5 A3.5 3.5 0 0 1 7 10.5 Z" fill={color} />
        </svg>
      );
    case 'VERIFICATION':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke={color} strokeWidth="1.5" />
          <path d="M7 3.5 A3.5 3.5 0 1 1 3.5 7 L7 7 Z" fill={color} />
        </svg>
      );
    case 'CLOSED':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6.25" fill={color} />
          <path d="M4.3 7.2 6.2 9 9.8 5.2" fill="none" stroke="var(--background)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case 'KNM_ESCALATION':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6.25" fill={color} />
          <path d="M7 3.8v3.9" stroke="var(--background)" strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="7" cy="10" r="0.95" fill="var(--background)" />
        </svg>
      );
  }
};

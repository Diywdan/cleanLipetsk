import React from 'react';
import { Badge } from '@/components/ui/badge';
import type { IncidentStatus } from '../types';

export const getStatusBadge = (currentStatus: IncidentStatus): React.ReactNode => {
  switch (currentStatus) {
    case 'NEW':
      return <Badge className="bg-blue-50 hover:bg-blue-100 text-blue-700 border-blue-200 font-semibold shadow-xs">Новый ИИ</Badge>;
    case 'IN_PROGRESS':
      return <Badge className="bg-amber-50 hover:bg-amber-100 text-amber-700 border-amber-200 font-semibold shadow-xs">В работе у УК</Badge>;
    case 'VERIFICATION':
      return <Badge className="bg-purple-50 hover:bg-purple-100 text-purple-700 border-purple-200 font-semibold shadow-xs">На проверке</Badge>;
    case 'CLOSED':
      return <Badge className="bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-200 font-semibold shadow-xs">Устранено</Badge>;
    case 'KNM_ESCALATION':
      return <Badge className="bg-rose-600 hover:bg-rose-700 text-white font-bold shadow-sm animate-pulse">Эскалация КНМ</Badge>;
    default:
      return null;
  }
};

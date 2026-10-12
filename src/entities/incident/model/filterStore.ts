import { useMemo } from 'react';
import { create } from 'zustand';
import type { IIncident, IncidentStatus } from '../types';
import { useIncidentStore } from './incidentStore';

// Фильтры реестра вынесены в стор: их делят таблица, лента «Диспетчерской»
// и боковое меню «Профинструмента».
export type PeriodFilter = 'all' | 'today' | '3days' | 'week';

export interface IncidentFilters {
  query: string;                    // адрес
  org: string;                      // название любой ответственной организации
  uprava: string;                   // 'all' или номер управы
  status: 'all' | IncidentStatus;
  period: PeriodFilter;
}

interface FilterStore extends IncidentFilters {
  set: (patch: Partial<IncidentFilters>) => void;
  reset: () => void;
}

const EMPTY: IncidentFilters = { query: '', org: '', uprava: 'all', status: 'all', period: 'all' };

export const useFilterStore = create<FilterStore>((set) => ({
  ...EMPTY,
  set: (patch) => set(patch),
  reset: () => set(EMPTY),
}));

const DAY_MS = 24 * 60 * 60 * 1000;

export function filterIncidents(
  incidents: IIncident[],
  f: IncidentFilters,
  options: { ignoreStatus?: boolean; now?: number } = {},
): IIncident[] {
  const now = options.now ?? Date.now();
  const query = f.query.trim().toLowerCase();
  const org = f.org.trim().toLowerCase();

  return incidents.filter((incident) => {
    if (query && !incident.location.address.toLowerCase().includes(query)) return false;
    if (org && !incident.responsibles.some((r) => r.organization.name.toLowerCase().includes(org))) {
      return false;
    }
    if (f.uprava !== 'all' && incident.location.upravaId !== Number(f.uprava)) return false;
    if (!options.ignoreStatus && f.status !== 'all' && incident.status !== f.status) return false;

    if (f.period !== 'all') {
      const created = new Date(incident.timeline.createdAt).getTime();
      if (f.period === 'today') {
        if (new Date(created).toDateString() !== new Date(now).toDateString()) return false;
      } else if (now - created > (f.period === '3days' ? 3 : 7) * DAY_MS) {
        return false;
      }
    }
    return true;
  });
}

export function hasActiveFilters(f: IncidentFilters): boolean {
  return Boolean(f.query || f.org || f.uprava !== 'all' || f.status !== 'all' || f.period !== 'all');
}

// Отфильтрованный список. ignoreStatus — для счётчиков по статусам: они
// показывают, сколько будет в каждой вкладке при остальных фильтрах.
export function useFilteredIncidents(options: { ignoreStatus?: boolean } = {}): IIncident[] {
  const incidents = useIncidentStore((s) => s.incidents);
  const query = useFilterStore((s) => s.query);
  const org = useFilterStore((s) => s.org);
  const uprava = useFilterStore((s) => s.uprava);
  const status = useFilterStore((s) => s.status);
  const period = useFilterStore((s) => s.period);
  const ignoreStatus = options.ignoreStatus ?? false;
  // Мемо: карта перерисовывает маркеры только при реальной смене списка
  return useMemo(
    () => filterIncidents(incidents, { query, org, uprava, status, period }, { ignoreStatus }),
    [incidents, query, org, uprava, status, period, ignoreStatus],
  );
}

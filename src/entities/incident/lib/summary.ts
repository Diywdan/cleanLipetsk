import type { IIncident } from '../types';

export interface IncidentSummary {
  open: number;     // всё, что не закрыто
  fresh: number;    // новые, ждут проверки инспектора
  overdue: number;  // в работе у исполнителя, срок уже истёк
  knm: number;      // переданы на контрольно-надзорное мероприятие
}

export function summarizeIncidents(incidents: IIncident[], now: number = Date.now()): IncidentSummary {
  return {
    open: incidents.filter((i) => i.status !== 'CLOSED').length,
    fresh: incidents.filter((i) => i.status === 'NEW').length,
    overdue: incidents.filter(
      (i) =>
        i.status === 'IN_PROGRESS' &&
        !!i.timeline.deadlineAt &&
        new Date(i.timeline.deadlineAt).getTime() < now,
    ).length,
    knm: incidents.filter((i) => i.status === 'KNM_ESCALATION').length,
  };
}

export function todayLabel(): string {
  return new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

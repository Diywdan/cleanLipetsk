import type { IIncident } from '@/entities/incident/types';
import type { IKpCard } from '../types';

const DAY = 86_400_000;

// Карточки для КП, которые встречаются в обращениях, но отсутствуют в справочнике
// (набор «Макет» и привязки «на лету»). Данные — из самого обращения.
export function kpFromIncidents(incidents: IIncident[], known: IKpCard[]): IKpCard[] {
  const have = new Set(known.map((k) => k.id));
  const out = new Map<string, IKpCard>();
  for (const i of incidents) {
    if (!i.kp || have.has(i.kp.kpId) || out.has(i.kp.kpId)) continue;
    out.set(i.kp.kpId, {
      id: i.kp.kpId,
      code: i.kp.code,
      registryNumber: i.kp.registryNumber,
      location: { ...i.location },
      responsibles: i.responsibles.map((r) => ({ role: r.role, organization: r.organization, confirmed: r.confirmed })),
      dataSource: 'MANUAL',
    });
  }
  return [...known, ...out.values()];
}

export interface KpStats {
  total: number;          // обращений по площадке за всё время
  last30: number;         // за 30 дней
  open: number;           // не закрыто сейчас
  knm: number;            // ушло на КНМ
  falsePositive: number;  // ложные срабатывания
  avgFixHours: number | null; // среднее время от подтверждения до закрытия
  lastAt: string | null;
}

export function kpStats(kpId: string, incidents: IIncident[], now: number): KpStats {
  const own = incidents.filter((i) => i.kp?.kpId === kpId);
  const fixed = own.filter((i) => i.timeline.closedAt && i.timeline.validatedAt && i.timeline.resolution !== 'FALSE_POSITIVE');
  const fixHours = fixed.map(
    (i) => (new Date(i.timeline.closedAt!).getTime() - new Date(i.timeline.validatedAt!).getTime()) / 3_600_000,
  );
  const last = own.map((i) => i.timeline.createdAt).sort().at(-1) ?? null;
  return {
    total: own.length,
    last30: own.filter((i) => now - new Date(i.timeline.createdAt).getTime() <= 30 * DAY).length,
    open: own.filter((i) => i.status !== 'CLOSED').length,
    knm: own.filter((i) => i.status === 'KNM_ESCALATION').length,
    falsePositive: own.filter((i) => i.timeline.resolution === 'FALSE_POSITIVE').length,
    avgFixHours: fixHours.length ? fixHours.reduce((a, b) => a + b, 0) / fixHours.length : null,
    lastAt: last,
  };
}

export function incidentsOfKp(kpId: string, incidents: IIncident[]): IIncident[] {
  return incidents
    .filter((i) => i.kp?.kpId === kpId)
    .sort((a, b) => new Date(b.timeline.createdAt).getTime() - new Date(a.timeline.createdAt).getTime());
}

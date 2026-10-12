import type { IIncident, IncidentSource, IncidentStatus } from '../types';
import { getPrimaryOrganizationName, getRecidivismCount } from './responsibles';
import { SOURCE_TITLE, typoQuotes } from './presentation';

// Выборки для панелей «Обстановка», сводок и аналитики.
// Всё считается из списка обращений; now передаётся явно, чтобы рендер был чистым.

const HOUR = 3_600_000;

export function isOverdue(i: IIncident, now: number): boolean {
  return i.status === 'IN_PROGRESS' && !!i.timeline.deadlineAt && new Date(i.timeline.deadlineAt).getTime() < now;
}

export function countByStatus(incidents: IIncident[]): Record<IncidentStatus, number> {
  const out: Record<IncidentStatus, number> = { NEW: 0, IN_PROGRESS: 0, VERIFICATION: 0, CLOSED: 0, KNM_ESCALATION: 0 };
  for (const i of incidents) out[i.status] += 1;
  return out;
}

export function createdWithin(incidents: IIncident[], hours: number, now: number): number {
  return incidents.filter((i) => now - new Date(i.timeline.createdAt).getTime() <= hours * HOUR).length;
}

// Исполнители, у которых сорваны сроки: просрочено в работе + передано на КНМ
export function failingExecutors(incidents: IIncident[], now: number) {
  const map = new Map<string, { name: string; overdue: number; knm: number; open: number }>();
  for (const i of incidents) {
    const name = typoQuotes(getPrimaryOrganizationName(i));
    const row = map.get(name) ?? { name, overdue: 0, knm: 0, open: 0 };
    if (i.status !== 'CLOSED') row.open += 1;
    if (isOverdue(i, now)) row.overdue += 1;
    if (i.status === 'KNM_ESCALATION') row.knm += 1;
    map.set(name, row);
  }
  return [...map.values()]
    .filter((r) => r.overdue + r.knm > 0)
    .sort((a, b) => b.overdue + b.knm - (a.overdue + a.knm) || b.open - a.open);
}

// В работе, срок ещё не вышел, но выйдет в ближайшие hours часов — ближайшие сверху
export function dueSoon(incidents: IIncident[], now: number, hours = 24, limit = 5) {
  return incidents
    .filter((i) => {
      if (i.status !== 'IN_PROGRESS' || !i.timeline.deadlineAt) return false;
      const left = new Date(i.timeline.deadlineAt).getTime() - now;
      return left > 0 && left <= hours * HOUR;
    })
    .sort((a, b) => new Date(a.timeline.deadlineAt!).getTime() - new Date(b.timeline.deadlineAt!).getTime())
    .slice(0, limit);
}

// Адреса, где нарушения повторяются (больше двух раз за месяц)
export function repeatAddresses(incidents: IIncident[], limit = 5) {
  return incidents
    .filter((i) => i.status !== 'CLOSED' && getRecidivismCount(i) > 2)
    .sort((a, b) => getRecidivismCount(b) - getRecidivismCount(a))
    .slice(0, limit)
    .map((i) => ({ id: i.id, address: i.location.address, count: getRecidivismCount(i), status: i.status }));
}

export function bySource(incidents: IIncident[]) {
  const map = new Map<IncidentSource, number>();
  for (const i of incidents) map.set(i.source, (map.get(i.source) ?? 0) + 1);
  return [...map.entries()]
    .map(([source, count]) => ({ source, title: SOURCE_TITLE[source], count }))
    .sort((a, b) => b.count - a.count);
}

// Поступление по дням за последние N дней (включая сегодня)
export function byDay(incidents: IIncident[], days: number, now: number) {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const buckets = Array.from({ length: days }, (_, k) => {
    const d = new Date(start.getTime() - (days - 1 - k) * 24 * HOUR);
    return {
      key: d.toDateString(),
      label: d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }).replace('.', ''),
      weekday: d.toLocaleDateString('ru-RU', { weekday: 'short' }),
      total: 0,
      closed: 0,
    };
  });
  const index = new Map(buckets.map((b, k) => [b.key, k]));
  for (const i of incidents) {
    const k = index.get(new Date(i.timeline.createdAt).toDateString());
    if (k === undefined) continue;
    buckets[k].total += 1;
    if (i.status === 'CLOSED') buckets[k].closed += 1;
  }
  return buckets;
}

// Сводка по исполнителям для аналитики
export function executorStats(incidents: IIncident[], now: number) {
  const map = new Map<string, { name: string; total: number; repeat: number; overdue: number; closed: number }>();
  for (const i of incidents) {
    const name = typoQuotes(getPrimaryOrganizationName(i));
    const row = map.get(name) ?? { name, total: 0, repeat: 0, overdue: 0, closed: 0 };
    row.total += 1;
    if (getRecidivismCount(i) > 2) row.repeat += 1;
    if (isOverdue(i, now) || i.status === 'KNM_ESCALATION') row.overdue += 1;
    if (i.status === 'CLOSED') row.closed += 1;
    map.set(name, row);
  }
  return [...map.values()].sort((a, b) => b.total - a.total);
}

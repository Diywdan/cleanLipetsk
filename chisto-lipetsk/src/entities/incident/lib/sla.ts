import type { IncidentSource } from '../types';

export type DeadlineHours = 24 | 48 | 72 | 720;

// Матрица SLA по регламенту ДРТ: для части источников срок задан жёстко,
// для остальных действует срок, который выбрал инспектор.
const FIXED_BY_SOURCE: Partial<Record<IncidentSource, DeadlineHours>> = {
  DIRECT_ORDER: 24,     // личное указание руководства — сутки
  GOVERNOR_PORTAL: 72,  // портал губернатора — 3 дня
  DELO_WEB: 720,        // Дело-web — до 30 дней
};

export function resolveDeadlineHours(source: IncidentSource, chosen: DeadlineHours): DeadlineHours {
  return FIXED_BY_SOURCE[source] ?? chosen;
}

export function isDeadlineFixed(source: IncidentSource): boolean {
  return source in FIXED_BY_SOURCE;
}

import type { IIncident } from '@/entities/incident/types';

// Минимальное обращение для тестов; поля переопределяются аргументом
export const T0 = Date.parse('2026-10-12T09:00:00Z');
export const HOUR = 3_600_000;

export function incident(over: Partial<IIncident> = {}): IIncident {
  const base: IIncident = {
    id: '0001',
    status: 'NEW',
    source: 'AI_CAMERA',
    priority: 'MEDIUM',
    location: { address: 'ул. Советская, 3', coordinates: [39.6, 52.61], upravaId: 4 },
    kp: { kpId: 'kp_001', code: 'LP-000120', score: 0.9, method: 'explicit' },
    responsibles: [
      {
        role: 'site_maintenance',
        organization: { id: 'uk_01', name: 'УК "Левобережная"', kind: 'UK' },
        confirmed: true,
        recidivismCount: 1,
      },
    ],
    timeline: { createdAt: new Date(T0 - 2 * HOUR).toISOString(), history: [] },
    media: { photoBeforeUrl: 'before.jpg', boundingBoxes: [] },
  };
  return { ...base, ...over, timeline: { ...base.timeline, ...over.timeline }, media: { ...base.media, ...over.media } };
}

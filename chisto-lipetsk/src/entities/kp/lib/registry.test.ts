import { describe, expect, it } from 'vitest';
import { incidentsOfKp, kpFromIncidents, kpStats } from './registry';
import { HOUR, T0, incident } from '@/test/fixtures';
import { distanceM } from '@/shared/lib/geo';
import { timeLeft } from '@/shared/lib/time';

const at = (ms: number) => new Date(ms).toISOString();
const DAY = 24 * HOUR;

describe('реестр КП', () => {
  const list = [
    incident({
      id: '1',
      status: 'CLOSED',
      timeline: { createdAt: at(T0 - 40 * DAY), validatedAt: at(T0 - 40 * DAY), closedAt: at(T0 - 40 * DAY + 10 * HOUR), resolution: 'FIXED' },
    }),
    incident({ id: '2', status: 'CLOSED', timeline: { createdAt: at(T0 - 3 * HOUR), closedAt: at(T0 - 2 * HOUR), resolution: 'FALSE_POSITIVE' } }),
    incident({ id: '3', status: 'KNM_ESCALATION', timeline: { createdAt: at(T0 - HOUR) } }),
    incident({ id: '4', kp: { kpId: 'kp_other', code: 'LP-1', score: 1, method: 'explicit' } }),
  ];

  it('статистика площадки', () => {
    expect(kpStats('kp_001', list, T0)).toMatchObject({ total: 3, last30: 2, open: 1, knm: 1, falsePositive: 1, avgFixHours: 10 });
  });

  it('история — новые сверху, только своя площадка', () => {
    expect(incidentsOfKp('kp_001', list).map((i) => i.id)).toEqual(['3', '2', '1']);
  });

  it('площадки из обращений дополняют справочник без дублей', () => {
    const cards = kpFromIncidents(list, []);
    expect(cards.map((c) => c.id).sort()).toEqual(['kp_001', 'kp_other']);
    expect(cards.every((c) => c.dataSource === 'MANUAL')).toBe(true);
  });
});

describe('утилиты', () => {
  it('расстояние: 0,001° широты ≈ 111 м', () => {
    expect(Math.round(distanceM([39.6, 52.61], [39.6, 52.611]))).toBe(111);
  });

  it('остаток срока словами', () => {
    expect(timeLeft(at(T0 + 30_000), T0).text).toBe('< 1 мин');
    expect(timeLeft(at(T0 + 5 * HOUR + 20 * 60_000), T0).text).toBe('5 ч 20 мин');
    expect(timeLeft(at(T0 + 50 * HOUR), T0).text).toBe('2 сут 2 ч');
    expect(timeLeft(at(T0 - 3 * HOUR), T0)).toMatchObject({ text: 'просрочено на 3 ч 0 мин', overdue: true });
  });
});

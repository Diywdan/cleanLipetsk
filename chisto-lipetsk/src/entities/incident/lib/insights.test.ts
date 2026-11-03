import { describe, expect, it } from 'vitest';
import { countByStatus, dueSoon, failingExecutors, isOverdue } from './insights';
import { isDeadlineFixed, resolveDeadlineHours } from './sla';
import { HOUR, T0, incident } from '@/test/fixtures';

const at = (ms: number) => new Date(ms).toISOString();
const inWork = (id: string, deadlineMs: number) =>
  incident({ id, status: 'IN_PROGRESS', timeline: { createdAt: at(T0), deadlineAt: at(deadlineMs) } });

describe('сроки и SLA', () => {
  it('фиксированные сроки по источнику', () => {
    expect(resolveDeadlineHours('GOVERNOR_PORTAL', 24)).toBe(72);
    expect(resolveDeadlineHours('DELO_WEB', 24)).toBe(720);
    expect(resolveDeadlineHours('AI_CAMERA', 24)).toBe(24);
    expect(isDeadlineFixed('DIRECT_ORDER')).toBe(true);
    expect(isDeadlineFixed('TSUR')).toBe(false);
  });

  it('просрочено — только дело в работе с прошедшим сроком', () => {
    expect(isOverdue(inWork('a', T0 - HOUR), T0)).toBe(true);
    const onCheck = incident({ status: 'VERIFICATION', timeline: { createdAt: at(T0), deadlineAt: at(T0 - HOUR) } });
    expect(isOverdue(onCheck, T0)).toBe(false);
  });

  it('срок выйдет за сутки: только будущие сроки в окне, ближайшие первыми', () => {
    const list = [
      inWork('a', T0 + 20 * HOUR),
      inWork('b', T0 + 2 * HOUR),
      inWork('c', T0 - HOUR),
      inWork('d', T0 + 30 * HOUR),
      incident({ id: 'e', status: 'VERIFICATION', timeline: { createdAt: at(T0), deadlineAt: at(T0 + HOUR) } }),
    ];
    expect(dueSoon(list, T0).map((i) => i.id)).toEqual(['b', 'a']);
  });
});

describe('сводки', () => {
  it('счёт по статусам', () => {
    const c = countByStatus([incident(), incident({ status: 'CLOSED' }), incident({ status: 'CLOSED' })]);
    expect(c).toMatchObject({ NEW: 1, CLOSED: 2, IN_PROGRESS: 0 });
  });

  it('исполнители со срывами: просрочка + КНМ', () => {
    const rows = failingExecutors([inWork('a', T0 - HOUR), incident({ status: 'KNM_ESCALATION' }), inWork('c', T0 + HOUR)], T0);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ name: 'УК «Левобережная»', overdue: 1, knm: 1, open: 3 });
  });
});

import { describe, expect, it } from 'vitest';
import { applyAction, availableActions, can, denyReason, WorkflowError, type Actor } from './workflow';
import { HOUR, T0, incident } from '@/test/fixtures';

const inspector: Actor = { kind: 'USER', role: 'INSPECTOR', name: 'Инспектор' };
const uk: Actor = { kind: 'USER', role: 'UK', name: 'Мастер' };
const admin: Actor = { kind: 'USER', role: 'ADMIN', name: 'Руководитель' };
const system: Actor = { kind: 'SYSTEM' };
const at = (ms: number) => new Date(ms).toISOString();

describe('маршрут дела: права', () => {
  it('новое дело подтверждает или отклоняет только инспектор', () => {
    const i = incident();
    expect(availableActions(i, inspector, T0)).toEqual(['CONFIRM', 'DISMISS']);
    expect(availableActions(i, uk, T0)).toEqual([]);
    expect(availableActions(i, admin, T0)).toEqual([]);
  });

  it('фотоотчёт отправляет только исполнитель и только в работе', () => {
    const work = incident({ status: 'IN_PROGRESS' });
    expect(can('SUBMIT_REPORT', work, uk, T0)).toBe(true);
    expect(can('SUBMIT_REPORT', work, inspector, T0)).toBe(false);
    expect(can('SUBMIT_REPORT', incident({ status: 'VERIFICATION' }), uk, T0)).toBe(false);
  });

  it('на КНМ — только после истечения срока', () => {
    const notYet = incident({ status: 'IN_PROGRESS', timeline: { createdAt: at(T0), deadlineAt: at(T0 + HOUR) } });
    const late = incident({ status: 'IN_PROGRESS', timeline: { createdAt: at(T0), deadlineAt: at(T0 - HOUR) } });
    expect(denyReason('ESCALATE', notYet, system, T0)).toBe('Срок устранения ещё не истёк');
    expect(can('ESCALATE', late, system, T0)).toBe(true);
    expect(can('ESCALATE', late, inspector, T0)).toBe(true);
    expect(can('ESCALATE', late, uk, T0)).toBe(false);
  });

  it('руководство только смотрит', () => {
    for (const status of ['NEW', 'IN_PROGRESS', 'VERIFICATION', 'KNM_ESCALATION', 'CLOSED'] as const) {
      expect(availableActions(incident({ status }), admin, T0)).toEqual([]);
    }
  });
});

describe('маршрут дела: переходы', () => {
  it('подтверждение ставит срок по выбору инспектора и пишет хронику', () => {
    const next = applyAction(incident(), 'CONFIRM', { deadlineHours: 48 }, inspector, T0);
    expect(next.status).toBe('IN_PROGRESS');
    expect(next.timeline.validatedAt).toBe(at(T0));
    expect(next.timeline.deadlineAt).toBe(at(T0 + 48 * HOUR));
    expect(next.timeline.history?.at(-1)?.title).toBe('Нарушение подтверждено');
  });

  it('для поручения руководства срок — сутки, что бы ни выбрал инспектор', () => {
    const next = applyAction(incident({ source: 'DIRECT_ORDER' }), 'CONFIRM', { deadlineHours: 72 }, inspector, T0);
    expect(next.timeline.deadlineAt).toBe(at(T0 + 24 * HOUR));
  });

  it('ложное срабатывание закрывает дело без исполнителя', () => {
    const next = applyAction(incident(), 'DISMISS', { reason: 'Повторное обращение' }, inspector, T0);
    expect(next.status).toBe('CLOSED');
    expect(next.timeline.resolution).toBe('FALSE_POSITIVE');
    expect(next.timeline.deadlineAt).toBeUndefined();
  });

  it('полный путь: подтвердить → отчёт → вернуть → отчёт → принять', () => {
    let i = applyAction(incident(), 'CONFIRM', { deadlineHours: 24 }, inspector, T0);
    const report = { photoUrl: 'after.jpg', takenAt: at(T0 + HOUR), distanceM: 40 };
    i = applyAction(i, 'SUBMIT_REPORT', { report }, uk, T0 + HOUR);
    expect(i.status).toBe('VERIFICATION');
    expect(i.media.photoAfterUrl).toBe('after.jpg');
    const deadline = i.timeline.deadlineAt;
    i = applyAction(i, 'RETURN', { comment: 'Остался навал' }, inspector, T0 + 2 * HOUR);
    expect(i.status).toBe('IN_PROGRESS');
    expect(i.timeline.deadlineAt).toBe(deadline); // возврат срок не продлевает
    i = applyAction(i, 'SUBMIT_REPORT', { report }, uk, T0 + 3 * HOUR);
    i = applyAction(i, 'APPROVE', {}, inspector, T0 + 4 * HOUR);
    expect(i.status).toBe('CLOSED');
    expect(i.timeline.resolution).toBe('FIXED');
    expect(i.timeline.history?.map((h) => h.type)).toEqual(['INSPECTOR', 'UK', 'INSPECTOR', 'UK', 'INSPECTOR']);
  });

  it('недопустимое действие бросает ошибку и не меняет дело', () => {
    const i = incident();
    expect(() => applyAction(i, 'APPROVE', {}, inspector, T0)).toThrow(WorkflowError);
    expect(i.status).toBe('NEW');
    expect(i.timeline.history).toEqual([]);
  });

  it('акт КНМ не меняет статус, но попадает в хронику', () => {
    const i = applyAction(incident({ status: 'KNM_ESCALATION' }), 'ISSUE_ACT', {}, inspector, T0);
    expect(i.status).toBe('KNM_ESCALATION');
    expect(i.timeline.history?.at(-1)?.title).toBe('Сформирован акт и предписание');
  });
});

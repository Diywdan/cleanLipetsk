import { describe, expect, it } from 'vitest';
import { isMismatch, reassignState, typeAfterExecutorChange } from './reassign';
import type { IExecutorRef } from '../types';

const EXECUTORS: IExecutorRef[] = [
  { id: 'EXEC-0001', name: 'ДДХиБ', kind: 'OMSU', types: [{ id: 'T-POTHOLES', name: 'Ямы' }, { id: 'T-BRANCHES', name: 'Ветки' }] },
  { id: 'EXEC-0002', name: 'Экопром', kind: 'REG_OPERATOR', types: [{ id: 'T-KGO', name: 'Вывоз КГО, ТКО' }] },
];
// Дело пришло с расхождением: Экопрому назначены «Ямы»
const current = { executorId: 'EXEC-0002', typeId: 'T-POTHOLES' };

describe('выбор исполнителя при подтверждении', () => {
  it('без изменений подтверждать можно, даже с расхождением; CRM ничего лишнего не получает', () => {
    const s = reassignState(EXECUTORS, current, current);
    expect(s).toMatchObject({ changed: false, valid: true, problem: null, payload: {} });
    expect(isMismatch(EXECUTORS, current)).toBe(true);
  });

  it('сменил ведомство на то, что отвечает за тип: уходит только executorId', () => {
    const s = reassignState(EXECUTORS, current, { executorId: 'EXEC-0001', typeId: 'T-POTHOLES' });
    expect(s).toMatchObject({ changed: true, valid: true, payload: { executorId: 'EXEC-0001' } });
    expect(s.types.map((t) => t.id)).toEqual(['T-POTHOLES', 'T-BRANCHES']);
  });

  it('сменил тип на тип своего ведомства: уходит только typeViolationId', () => {
    const s = reassignState(EXECUTORS, current, { executorId: 'EXEC-0002', typeId: 'T-KGO' });
    expect(s).toMatchObject({ valid: true, payload: { typeViolationId: 'T-KGO' } });
  });

  it('пара «ведомство — чужой тип» не пускает подтверждение', () => {
    const s = reassignState(EXECUTORS, { executorId: 'EXEC-0001', typeId: 'T-POTHOLES' }, { executorId: 'EXEC-0001', typeId: 'T-KGO' });
    expect(s.valid).toBe(false);
    expect(s.problem).toMatch(/тип нарушения/);
  });

  it('после смены ведомства тип сохраняется, только если новое ведомство за него отвечает', () => {
    expect(typeAfterExecutorChange(EXECUTORS, 'EXEC-0001', 'T-POTHOLES')).toBe('T-POTHOLES');
    expect(typeAfterExecutorChange(EXECUTORS, 'EXEC-0002', 'T-POTHOLES')).toBe('');
    expect(reassignState(EXECUTORS, current, { executorId: 'EXEC-0001', typeId: '' }).valid).toBe(false);
  });
});

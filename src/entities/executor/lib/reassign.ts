import type { IExecutorRef, IViolationTypeRef } from '../types';

// Выбор исполнителя и типа нарушения при подтверждении дела. Правило то же, что проверяет CRM:
// ведомство должно отвечать за выбранный тип. Оставить как пришло можно, если исполнитель и тип
// есть, — CRM запишет в хронику, что инспектор принял расхождение со справочниками. Проблема
// из домовых чатов может прийти без них: тогда без выбора подтвердить нельзя.

export interface ReassignChoice {
  executorId: string;
  typeId: string; // '' — тип ещё не выбран
}

export interface ReassignState {
  types: IViolationTypeRef[]; // типы выбранного ведомства
  changed: boolean;
  valid: boolean;
  problem: string | null;
  // Тело для CRM: только то, что инспектор поменял
  payload: { executorId?: string; typeViolationId?: string };
}

export function reassignState(executors: IExecutorRef[], current: ReassignChoice, chosen: ReassignChoice): ReassignState {
  const executor = executors.find((x) => x.id === chosen.executorId);
  const types = executor?.types ?? [];
  const changed = chosen.executorId !== current.executorId || chosen.typeId !== current.typeId;
  const base = { types, changed, payload: {} };
  if (!changed) {
    const missing = !current.executorId ? 'Выберите исполнителя' : !current.typeId ? 'Выберите тип нарушения' : null;
    return { ...base, valid: missing === null, problem: missing };
  }
  if (!executor) return { ...base, valid: false, problem: 'Выберите исполнителя' };
  if (!types.some((t) => t.id === chosen.typeId)) {
    return { ...base, valid: false, problem: 'Выберите тип нарушения: этот исполнитель отвечает только за свои типы' };
  }
  const payload: ReassignState['payload'] = {};
  if (chosen.executorId !== current.executorId) payload.executorId = chosen.executorId;
  if (chosen.typeId !== current.typeId) payload.typeViolationId = chosen.typeId;
  return { ...base, valid: true, problem: null, payload };
}

// Сменили ведомство: тип остаётся, если новое ведомство за него отвечает, иначе его надо выбрать заново
export function typeAfterExecutorChange(executors: IExecutorRef[], executorId: string, typeId: string): string {
  const types = executors.find((x) => x.id === executorId)?.types ?? [];
  return types.some((t) => t.id === typeId) ? typeId : '';
}

// Пришедшее дело не сходится со справочником: тип не из списка своего ведомства
export function isMismatch(executors: IExecutorRef[], choice: ReassignChoice): boolean {
  const executor = executors.find((x) => x.id === choice.executorId);
  return !executor || !executor.types.some((t) => t.id === choice.typeId);
}

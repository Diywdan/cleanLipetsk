import type { IHistoryEvent, IIncident, IncidentStatus, IPhotoReport } from '../types';
import type { UserRole } from '@/entities/user/types';
import { resolveDeadlineHours, type DeadlineHours } from './sla';

// ─────────────────────────────────────────────────────────────────────────────
// Маршрут дела: кто, из какого статуса и что может сделать. Единственное место,
// где описаны переходы, — стор, API-макет, кнопки карточки и тесты берут правила отсюда.
// Бэкенд обязан проверять те же правила у себя; здесь — зеркало для интерфейса.
// ─────────────────────────────────────────────────────────────────────────────

export type IncidentAction =
  | 'CONFIRM'        // инспектор подтвердил нарушение и направил исполнителю, пошёл срок
  | 'DISMISS'        // инспектор признал сигнал ложным, дело закрыто без исполнителя
  | 'SUBMIT_REPORT'  // мастер УК приложил фотоотчёт «стало»
  | 'APPROVE'        // инспектор принял работу, дело закрыто
  | 'RETURN'         // инспектор вернул на доработку, срок не продлевается
  | 'ESCALATE'       // срок вышел — материалы на КНМ (система по таймеру или инспектор)
  | 'ISSUE_ACT';     // инспектор сформировал акт и предписание, статус не меняется

export type Actor =
  | { kind: 'USER'; role: UserRole; name: string; organizationName?: string }
  | { kind: 'SYSTEM' };

export type ActionPayload = {
  CONFIRM: { deadlineHours: DeadlineHours };
  DISMISS: { reason?: string };
  SUBMIT_REPORT: { report: IPhotoReport };
  APPROVE: Record<string, never>;
  RETURN: { comment?: string };
  ESCALATE: Record<string, never>;
  ISSUE_ACT: Record<string, never>;
};

interface Rule {
  title: string;
  from: IncidentStatus[];
  to: IncidentStatus | null;           // null — статус не меняется
  roles: (UserRole | 'SYSTEM')[];
  // Дополнительное условие; возвращает причину отказа или null
  guard?: (incident: IIncident, now: number) => string | null;
}

const deadlinePassed = (i: IIncident, now: number) =>
  !!i.timeline.deadlineAt && new Date(i.timeline.deadlineAt).getTime() <= now;

export const RULES: Record<IncidentAction, Rule> = {
  CONFIRM: { title: 'Подтвердить и направить исполнителю', from: ['NEW'], to: 'IN_PROGRESS', roles: ['INSPECTOR'] },
  DISMISS: { title: 'Ложное срабатывание', from: ['NEW'], to: 'CLOSED', roles: ['INSPECTOR'] },
  SUBMIT_REPORT: {
    title: 'Отправить фотоотчёт',
    from: ['IN_PROGRESS'],
    to: 'VERIFICATION',
    roles: ['UK'],
  },
  APPROVE: { title: 'Принять и закрыть', from: ['VERIFICATION'], to: 'CLOSED', roles: ['INSPECTOR'] },
  RETURN: { title: 'Вернуть на доработку', from: ['VERIFICATION'], to: 'IN_PROGRESS', roles: ['INSPECTOR'] },
  ESCALATE: {
    title: 'Передать на КНМ',
    from: ['IN_PROGRESS'],
    to: 'KNM_ESCALATION',
    roles: ['SYSTEM', 'INSPECTOR'],
    guard: (i, now) => (deadlinePassed(i, now) ? null : 'Срок устранения ещё не истёк'),
  },
  ISSUE_ACT: { title: 'Сформировать акт и предписание', from: ['KNM_ESCALATION'], to: null, roles: ['INSPECTOR'] },
};

export class WorkflowError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WorkflowError';
  }
}

const actorRole = (a: Actor): UserRole | 'SYSTEM' => (a.kind === 'SYSTEM' ? 'SYSTEM' : a.role);

// Почему действие недоступно; null — можно
export function denyReason(action: IncidentAction, incident: IIncident, actor: Actor, now: number): string | null {
  const rule = RULES[action];
  if (!rule.roles.includes(actorRole(actor))) return 'Действие недоступно для вашей роли';
  if (!rule.from.includes(incident.status)) return 'Действие недоступно в текущем статусе дела';
  return rule.guard?.(incident, now) ?? null;
}

export function can(action: IncidentAction, incident: IIncident, actor: Actor, now: number): boolean {
  return denyReason(action, incident, actor, now) === null;
}

// Действия, доступные роли для дела, — для кнопок и подсказок
export function availableActions(incident: IIncident, actor: Actor, now: number): IncidentAction[] {
  return (Object.keys(RULES) as IncidentAction[]).filter((a) => can(a, incident, actor, now));
}

const HOUR = 3_600_000;

function historyEvent(incident: IIncident, actor: Actor, at: string, title: string, description: string): IHistoryEvent {
  const n = (incident.timeline.history?.length ?? 0) + 1;
  const type: IHistoryEvent['type'] =
    actor.kind === 'SYSTEM' ? 'SYSTEM' : actor.role === 'UK' ? 'UK' : 'INSPECTOR';
  return { id: `h${n}`, timestamp: at, title, description, type };
}

function executorName(i: IIncident): string {
  return i.responsibles.find((r) => r.role === 'site_maintenance')?.organization.name ?? 'исполнителю';
}

// Применить действие: новое дело с новым статусом, сроками и записью в хронике.
// Чистая функция — не мутирует вход, бросает WorkflowError, если правило не пускает.
export function applyAction<A extends IncidentAction>(
  incident: IIncident,
  action: A,
  payload: ActionPayload[A],
  actor: Actor,
  now: number,
): IIncident {
  const reason = denyReason(action, incident, actor, now);
  if (reason) throw new WorkflowError(reason);

  const at = new Date(now).toISOString();
  const rule = RULES[action];
  const next: IIncident = {
    ...incident,
    status: rule.to ?? incident.status,
    timeline: { ...incident.timeline, history: [...(incident.timeline.history ?? [])] },
    media: { ...incident.media },
  };
  const log = (title: string, description: string) => next.timeline.history!.push(historyEvent(incident, actor, at, title, description));

  switch (action) {
    case 'CONFIRM': {
      const { deadlineHours } = payload as ActionPayload['CONFIRM'];
      const hours = resolveDeadlineHours(incident.source, deadlineHours);
      next.timeline.validatedAt = at;
      next.timeline.deadlineAt = new Date(now + hours * HOUR).toISOString();
      log('Нарушение подтверждено', `Уведомление направлено: ${executorName(incident)}, срок ${hours} ч.`);
      break;
    }
    case 'DISMISS': {
      const { reason: why } = payload as ActionPayload['DISMISS'];
      next.timeline.closedAt = at;
      next.timeline.resolution = 'FALSE_POSITIVE';
      log('Ложное срабатывание', why ? `Сигнал не подтверждён: ${why}.` : 'Сигнал не подтверждён, исполнителю не направлялся.');
      break;
    }
    case 'SUBMIT_REPORT': {
      const { report } = payload as ActionPayload['SUBMIT_REPORT'];
      next.media.photoAfterUrl = report.photoUrl;
      next.media.report = report;
      const where = report.distanceM == null ? 'место съёмки не определено' : `${Math.round(report.distanceM)} м от площадки`;
      log('Фотоотчёт исполнителя', `Снимок убранной площадки, ${where}.`);
      break;
    }
    case 'APPROVE':
      next.timeline.closedAt = at;
      next.timeline.resolution = 'FIXED';
      log('Дело закрыто', 'Инспектор принял работу.');
      break;
    case 'RETURN': {
      const { comment } = payload as ActionPayload['RETURN'];
      log('Возвращено на доработку', comment ? comment : 'Работа не принята, срок не продлевается.');
      break;
    }
    case 'ESCALATE':
      log('Срок истёк', 'Материалы переданы на контрольно-надзорное мероприятие.');
      break;
    case 'ISSUE_ACT':
      log('Сформирован акт и предписание', 'Документы выгружены в PDF.');
      break;
  }
  return next;
}

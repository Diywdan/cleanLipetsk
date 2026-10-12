import type { IIncident } from '../types';
import { applyAction, type ActionPayload, type Actor, type IncidentAction } from '../lib/workflow';
import { API_URL, http } from '@/shared/api/http';
import { readJson, removeKey, writeJson } from '@/shared/api/storage';

// ─────────────────────────────────────────────────────────────────────────────
// Контракт работы с обращениями. Интерфейс вызывает только эти методы;
// реализация — макет в браузере (стенд) или HTTP к бэкенду (VITE_API_URL).
// Описание эндпоинтов для бэкенда — docs/api-contract.md.
// ─────────────────────────────────────────────────────────────────────────────

export interface IncidentApi {
  list(): Promise<IIncident[]>;
  // Действие по маршруту дела. Бэкенд сам определяет автора по сессии и проверяет права;
  // actor здесь нужен макету, HTTP-реализация его не отправляет.
  act<A extends IncidentAction>(id: string, action: A, payload: ActionPayload[A], actor: Actor): Promise<IIncident>;
  // Только для стенда: вернуть исходный набор
  reset?(): Promise<IIncident[]>;
  // Сохраняются ли изменения между перезагрузками (для подсказки на стенде)
  readonly persistent: boolean;
}

// ── Макет: данные в памяти + localStorage ───────────────────────────────────
export function createMockIncidentApi(storageKey: string, seed: () => IIncident[]): IncidentApi {
  let data: IIncident[] = readJson<IIncident[]>(storageKey) ?? seed();
  let persistent = true;
  const save = () => {
    persistent = writeJson(storageKey, data);
  };

  return {
    get persistent() {
      return persistent;
    },
    async list() {
      return data.map((i) => ({ ...i }));
    },
    async act(id, action, payload, actor) {
      const current = data.find((i) => i.id === id);
      if (!current) throw new Error(`Обращение ${id} не найдено`);
      const next = applyAction(current, action, payload, actor, Date.now());
      data = data.map((i) => (i.id === id ? next : i));
      save();
      return next;
    },
    async reset() {
      removeKey(storageKey);
      data = seed();
      persistent = true;
      return data.map((i) => ({ ...i }));
    },
  };
}

// ── Бэкенд ──────────────────────────────────────────────────────────────────
const ACTION_PATH: Record<IncidentAction, string> = {
  CONFIRM: 'confirm',
  DISMISS: 'dismiss',
  SUBMIT_REPORT: 'report',
  APPROVE: 'approve',
  RETURN: 'return',
  ESCALATE: 'escalate',
  ISSUE_ACT: 'act',
};

export function createHttpIncidentApi(baseUrl: string): IncidentApi {
  return {
    persistent: true,
    list: () => http<IIncident[]>(baseUrl, '/incidents'),
    act: (id, action, payload) =>
      http<IIncident>(baseUrl, `/incidents/${encodeURIComponent(id)}/${ACTION_PATH[action]}`, { method: 'POST', body: payload }),
  };
}

// Версия демо-набора: поменяли генератор — увеличьте, иначе сохранённое в браузере перекроет новые данные
const DEMO_DATA_VERSION = 2;

export function createIncidentApi(dataset: string, seed: () => IIncident[]): IncidentApi {
  return API_URL ? createHttpIncidentApi(API_URL) : createMockIncidentApi(`chisto.demo.v${DEMO_DATA_VERSION}.${dataset}`, seed);
}

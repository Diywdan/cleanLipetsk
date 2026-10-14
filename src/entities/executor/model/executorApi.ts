import type { IExecutorRef } from '../types';
import type { OrganizationKind } from '@/entities/incident/types';
import { API_URL, http } from '@/shared/api/http';

// Справочник ведомств и типов нарушений. Ведёт его CRM — тот же, что читает Data Gateway;
// инспектору он нужен, чтобы поправить исполнителя или тип при подтверждении дела.
export interface ExecutorApi {
  list(): Promise<IExecutorRef[]>;
}

// Ответ CRM на GET /executors — справочник админки, поля в snake_case
interface CrmExecutor {
  executor_id: string;
  name: string;
  kind: OrganizationKind;
  is_active: boolean;
  violation_types: { type_violation_id: string; name: string; is_active: boolean }[];
}

export function createHttpExecutorApi(baseUrl: string): ExecutorApi {
  return {
    list: async () =>
      (await http<CrmExecutor[]>(baseUrl, '/executors'))
        .filter((x) => x.is_active)
        .map((x) => ({
          id: x.executor_id,
          name: x.name,
          kind: x.kind,
          types: x.violation_types.filter((t) => t.is_active).map((t) => ({ id: t.type_violation_id, name: t.name })),
        })),
  };
}

// На стенде без бэкенда справочника нет: исполнитель и тип в макете не меняются
export function createExecutorApi(): ExecutorApi {
  return API_URL ? createHttpExecutorApi(API_URL) : { list: async () => [] };
}

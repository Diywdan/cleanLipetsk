import type { OrganizationKind } from '@/entities/incident/types';

// Ведомство-исполнитель из справочника CRM и типы нарушений, за которые оно отвечает
export interface IViolationTypeRef {
  id: string;
  name: string;
}

export interface IExecutorRef {
  id: string;
  name: string;
  kind: OrganizationKind;
  types: IViolationTypeRef[];
}

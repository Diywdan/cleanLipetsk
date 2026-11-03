import type { IIncident, IResponsible, OrganizationKind, ResponsibleRole } from '../types';

export const RESPONSIBLE_ROLE_TITLE: Record<ResponsibleRole, string> = {
  site_maintenance: 'Содержание площадки',
  waste_removal: 'Вывоз',
  new_site_decision: 'Создание и перенос КП',
  territory: 'Прилегающая территория',
  supervision: 'Надзор',
};

export const ORGANIZATION_KIND_TITLE: Record<OrganizationKind, string> = {
  UK: 'УК',
  REG_OPERATOR: 'Региональный оператор',
  OMSU: 'ОМСУ',
  DRT: 'ДРТ',
  UPRAVA: 'Управа',
  MPR: 'Минприроды',
  GZHI: 'ГЖИ',
};

// Основной исполнитель заявки — тот, кто содержит площадку: ему уходит предписание,
// по нему считается статистика УК. Если такого нет — первый в списке.
export function getPrimaryResponsible(incident: IIncident): IResponsible | undefined {
  return (
    incident.responsibles.find((r) => r.role === 'site_maintenance') ?? incident.responsibles[0]
  );
}

export function getPrimaryOrganizationName(incident: IIncident): string {
  return getPrimaryResponsible(incident)?.organization.name ?? 'Не определён';
}

export function getRecidivismCount(incident: IIncident): number {
  return getPrimaryResponsible(incident)?.recidivismCount ?? 0;
}

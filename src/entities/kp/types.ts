import type { IGeoLocation, IResponsible } from '@/entities/incident/types';

// Карточка контейнерной площадки (КП) из справочника.
// Источник истины по реестру ещё не выбран (CRM или сервис справочника КП) —
// интерфейс берёт карточки через kpApi, а не напрямую из данных.

export type KpDataSource = 'FGIS_UTKO' | 'FIELD_CHECK' | 'MANUAL';

export interface IKpContainers {
  tko: number;        // баки ТКО
  separate: number;   // раздельный сбор
  kgmBay: boolean;    // бункер или отсек под КГМ
}

export interface IKpCard {
  id: string;                 // постоянный ID карточки
  code: string;               // LP-000123
  registryNumber?: string;    // номер в реестре мест накопления
  location: Omit<IGeoLocation, 'houseFias'>;
  containers?: IKpContainers;
  surface?: 'ASPHALT' | 'CONCRETE' | 'SOIL';
  fenced?: boolean;
  responsibles: Omit<IResponsible, 'recidivismCount'>[];
  dataSource: KpDataSource;
  checkedAt?: string;         // последняя полевая проверка
}

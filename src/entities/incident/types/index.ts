// 1. Фиксируем все этапы маршрутной карты из документов аналитиков
export type IncidentStatus = 
  | 'NEW'             // Выявлено ИИ, ждет проверки инспектора (таймер 24ч)
  | 'IN_PROGRESS'     // Подтверждено, передано в УК (таймер 24-72ч)
  | 'VERIFICATION'    // УК загрузила фотоотчет "Стало", инспектор проверяет
  | 'CLOSED'          // Нарушение успешно устранено (Цель достигнута)
  | 'KNM_ESCALATION'; // Срок вышел, материалы переданы в надзорный контур (ГЖИ/Минприроды)

// 2. Маркируем источники сигналов для фильтрации на карте и в списках
export type IncidentSource = 
  // ─── Базовый пилотный контур ───
  | 'AI_CAMERA'           // Автоматические ИИ-камеры благоустройства
  | 'TSUR'                // Сигналы Центра управления регионом (ЦУР)
  | 'SED'                 // Старая система электронного документооборота
  | 'OMSU_CHAT'           // Оперативный внутренний чат ОМСУ
  | 'INSPECTION'          // Ручная фиксация инженером во время обхода
  
  // ─── Расширенный контур регламента ДРТ ───
  | 'DELO_WEB'            // Система «Дело-web» (официальные письма)
  | 'GOVERNOR_PORTAL'     // Портал губернатора Липецкой области
  | 'HOUSE_CHATS'         // Общедомовые чаты жителей
  | 'MAKS_CHAT'           // Чат ДРТ в мессенджере «Макс» (от канцелярии)
  | 'DRT_WEBSITE'         // Обращения с официального сайта ДРТ
  | 'DIRECT_ORDER';       // Личное указание руководства ДРТ (Высший приоритет) 

// 3. Структура ИИ-разметки (Bounding Box) для отрисовки поверх фото нарушения
export interface IBoundingBox {
  id: string;
  label: string;       // Например: "Переполнение бака", "Навал КГМ"
  confidence: number;  // Точность распознавания нейросетью (0.00 - 1.00)
  // Процентные координаты (0-100) для идеальной адаптивности на фронтенде
  x: number; 
  y: number;
  width: number;
  height: number;
}

// 4. Гео-данные для твоей Интерактивной карты Липецка
export interface IGeoLocation {
  address: string;
  // [долгота, широта] — порядок Яндекс Карт v3. ФГИС УТКО и большинство реестров отдают
  // широту первой: при загрузке реальных данных пару нужно развернуть.
  coordinates: [number, number];
  cadastralNumber?: string;      // Кадастровый номер для подсветки полигона ответственности УК
  upravaId: number; // номер управы
  houseFias?: string;            // ФИАС дома, если сигнал пришёл по дому (домовой чат, ПОС)
}

// 5. Привязка к контейнерной площадке из справочника КП.
// Справочник ведётся отдельно (ФГИС УТКО + полевые проверки), здесь — только ссылка на карточку.
export type KpMatchMethod =
  | 'explicit'        // КП указана явно: бот ДРТ, код LP-…, GUID УТКО
  | 'registry_house'  // основная КП дома по реестру или полевой проверке
  | 'address_anchor'  // «в районе д. N» в адресе КП
  | 'nearest_single'  // единственная КП рядом с домом
  | 'nearest_multi'   // ближайшая по геометке фото
  | 'text_hint'       // выбрана по подсказке в тексте («за домом», «у школы»)
  | 'manual';

export interface IKpLink {
  kpId: string;             // постоянный ID карточки КП
  code: string;             // короткий код для бота и общения: LP-000123
  registryNumber?: string;  // номер в реестре мест накопления (0003709-48)
  score: number;            // уверенность сопоставления, 0..1; ниже 0.75 — заявка ведётся на дом
  method: KpMatchMethod;
}

// Тема ЕДС: вместе с КП задаёт ключ заявки (события одной КП и одной темы склеиваются)
export interface IEdsTheme {
  code: string;   // например "14:434135041"
  title: string;  // «Состояние КП»
}

// 6. Организации и ответственные. Ответственных несколько, у каждого своя роль:
// вывоз — региональный оператор, содержание площадки — УК или собственник КП.
export type OrganizationKind = 'UK' | 'REG_OPERATOR' | 'OMSU' | 'DRT' | 'UPRAVA' | 'MPR' | 'GZHI';

export interface IOrganization {
  id: string;
  name: string;            // Например: "УК Левобережная"
  kind: OrganizationKind;
  directorName?: string;
  phone?: string;
  email?: string;
}

export type ResponsibleRole =
  | 'site_maintenance'   // содержание площадки и уборка вокруг
  | 'waste_removal'      // вывоз
  | 'new_site_decision'  // создание и перенос площадки
  | 'territory'          // прилегающая территория
  | 'supervision';       // надзор

export interface IResponsible {
  role: ResponsibleRole;
  organization: IOrganization;
  confirmed: boolean;       // подтверждено документом или полевой проверкой
  recidivismCount: number;  // Метрика повторности нарушений по этому адресу
}

// 7. Таймлайн оперативного дела (для соблюдения KPI до 5 суток)
export interface IIncidentTimeline {
  createdAt: string;       // Время поступления сигнала
  validatedAt?: string;    // Время подтверждения инспектором (Цель: до 1 суток)
  deadlineAt?: string;     // Динамический дедлайн для УК (24-72ч)
  closedAt?: string;       // Время закрытия инцидента
  resolution?: 'FIXED' | 'FALSE_POSITIVE'; // чем закрыто: устранено или сигнал не подтвердился
  history?: IHistoryEvent[];
}

export interface IHistoryEvent {
  id: string;
  timestamp: string;
  title: string;
  description: string;
  type: 'AI' | 'INSPECTOR' | 'UK' | 'SYSTEM';
}

// Фотоотчёт исполнителя: снимок и где/когда он сделан — по этому инспектор судит, что снято на месте
export interface IPhotoReport {
  photoUrl: string;
  takenAt: string;               // время съёмки (из файла) или отправки
  coords?: [number, number];     // [долгота, широта] телефона в момент отправки
  distanceM?: number;            // расстояние до площадки, м
  comment?: string;
}

// 8. Единый монолитный интерфейс инцидента (Главная сущность системы)
export interface IIncident {
  id: string;
  status: IncidentStatus;
  source: IncidentSource;
  priority: 'LOW' | 'MEDIUM' | 'HIGH';
  location: IGeoLocation;
  kp: IKpLink | null;       // null — КП не определена, заявка висит на доме
  edsTheme?: IEdsTheme;
  responsibles: IResponsible[];
  timeline: IIncidentTimeline;
  media: {
    photoBeforeUrl: string;   // Снимок нарушения от ИИ
    photoAfterUrl?: string;   // Снимок убранной площадки от УК
    report?: IPhotoReport;    // подробности фотоотчёта
    boundingBoxes: IBoundingBox[];
  };
  // Отдаёт CRM для сообщений инженера из бота ДРТ: ИИ-разметки там нет, нарушение выбрал человек
  violationType?: { id: string; name: string | null };
  comment?: string | null;
  reviewReason?: string | null; // событие не сошлось со справочниками — инспектор проверяет исполнителя
}

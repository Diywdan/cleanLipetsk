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
  coordinates: [number, number]; // [широта, долгота] для Яндекс Карт
  cadastralNumber?: string;      // Кадастровый номер для подсветки полигона ответственности УК
  upravaId: number; // номер управы
}

// 5. Данные из Единого реестра контактов и объектов благоустройства
export interface IResponsibleParty {
  id: string;
  organizationName: string; // Например: "УК Левобережная"
  directorName: string;
  phone: string;
  email: string;
  recidivismCount: number;  // Метрика повторности нарушений по этому адресу
}

// 6. Таймлайн оперативного дела (для соблюдения KPI до 5 суток)
export interface IIncidentTimeline {
  createdAt: string;       // Время поступления сигнала
  validatedAt?: string;    // Время подтверждения инспектором (Цель: до 1 суток)
  deadlineAt?: string;     // Динамический дедлайн для УК (24-72ч)
  closedAt?: string;       // Время закрытия инцидента
  history?: IHistoryEvent[];
}

export interface IHistoryEvent {
  id: string;
  timestamp: string;
  title: string;
  description: string;
  type: 'AI' | 'INSPECTOR' | 'UK' | 'SYSTEM';
}

// 7. Единый монолитный интерфейс инцидента (Главная сущность системы)
export interface IIncident {
  id: string;
  status: IncidentStatus;
  source: IncidentSource;
  priority: 'LOW' | 'MEDIUM' | 'HIGH';
  location: IGeoLocation;
  responsible: IResponsibleParty;
  timeline: IIncidentTimeline;
  media: {
    photoBeforeUrl: string;   // Снимок нарушения от ИИ
    photoAfterUrl?: string;   // Снимок убранной площадки от УК
    boundingBoxes: IBoundingBox[];
  };
}

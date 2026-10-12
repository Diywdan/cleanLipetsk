import type { IncidentSource, IncidentStatus } from '../types';

// Один словарь вида статусов на всё приложение: тег в таблице и карточке,
// маркер на карте, легенда и графики берут цвета отсюда.
// text — для надписей (контраст 4.5+ на bg), dot — для точек, маркеров и графиков.
export interface StatusMeta {
  label: string;
  text: string;
  bg: string;
  dot: string;
}

export const STATUS_META: Record<IncidentStatus, StatusMeta> = {
  NEW: { label: 'Новое', text: '#0D4CD3', bg: '#E8EFFC', dot: '#0D4CD3' },
  IN_PROGRESS: { label: 'В работе', text: '#8A5300', bg: '#FFF3DC', dot: '#E89B0C' },
  VERIFICATION: { label: 'На проверке', text: '#5B3FB0', bg: '#EFEBFA', dot: '#7B61D1' },
  CLOSED: { label: 'Устранено', text: '#0A6B34', bg: '#E5F4EB', dot: '#12A150' },
  KNM_ESCALATION: { label: 'Передано на КНМ', text: '#BE1B33', bg: '#FCEBED', dot: '#EE3F58' },
};

export const STATUS_ORDER: IncidentStatus[] = [
  'NEW',
  'IN_PROGRESS',
  'VERIFICATION',
  'KNM_ESCALATION',
  'CLOSED',
];

export const SOURCE_TITLE: Record<IncidentSource, string> = {
  AI_CAMERA: 'Камера с ИИ',
  TSUR: 'ЦУР',
  SED: 'СЭД',
  OMSU_CHAT: 'Чат ОМСУ',
  INSPECTION: 'Обход инспектора',
  DELO_WEB: 'Дело-web',
  GOVERNOR_PORTAL: 'Портал губернатора',
  HOUSE_CHATS: 'Домовой чат',
  MAKS_CHAT: 'Чат ДРТ в MAX',
  DRT_WEBSITE: 'Сайт ДРТ',
  DIRECT_ORDER: 'Поручение руководства',
};

export function formatDeadline(hours: number): string {
  if (hours === 24) return '1 сутки';
  if (hours % 24 === 0) return `${hours / 24} суток`;
  return `${hours} ч`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Прямые кавычки из реестров → «ёлочки»: ООО "Ромашка" → ООО «Ромашка»
export function typoQuotes(text: string): string {
  return text.replace(/"([^"]*)"/g, '«$1»');
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU');
}

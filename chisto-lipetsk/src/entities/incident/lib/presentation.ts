import type { IncidentSource, IncidentStatus } from '../types';

// Один словарь вида статусов на всё приложение: тег в таблице и карточке,
// маркер на карте, легенда и графики. Цвета — переменные темы (styles/themes.css),
// поэтому статус перекрашивается вместе с темой.
// text — надписи на подложке bg (контраст 4.5+), dot — точки, маркеры, графики.
export interface StatusMeta {
  label: string;
  short: string;
  cssVar: string;  // имя переменной точки, для мест, где нужен реальный цвет (SVG)
  text: string;
  bg: string;
  dot: string;
}

function meta(label: string, short: string, key: string): StatusMeta {
  return {
    label,
    short,
    cssVar: `--st-${key}`,
    text: `var(--st-${key}-fg)`,
    bg: `var(--st-${key}-bg)`,
    dot: `var(--st-${key})`,
  };
}

export const STATUS_META: Record<IncidentStatus, StatusMeta> = {
  NEW: meta('Новое', 'Новые', 'new'),
  IN_PROGRESS: meta('В работе', 'В работе', 'work'),
  VERIFICATION: meta('На проверке', 'Проверка', 'check'),
  CLOSED: meta('Устранено', 'Устранено', 'done'),
  KNM_ESCALATION: meta('Передано на КНМ', 'КНМ', 'knm'),
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

// «Инспектор ДРТ» → «инспектор ДРТ»: аббревиатуры остаются заглавными
export function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

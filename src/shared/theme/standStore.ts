import { create } from 'zustand';

// Демонстрационный стенд: три направления дизайна и базовая гос-тема.
// Тема живёт в атрибуте data-theme на <html> — от него зависят токены в themes.css.
export type ThemeId = 'dispatch' | 'dossier' | 'pro' | 'gos';
export type DatasetId = 'demo' | 'mock';

export const THEMES: { id: ThemeId; title: string; hint: string }[] = [
  { id: 'dispatch', title: 'Диспетчерская', hint: 'Ситуационный центр: карта на весь экран, тёмная тема' },
  { id: 'dossier', title: 'Досье', hint: 'Сводка в газетной манере: бумага, засечки, служебная записка' },
  { id: 'pro', title: 'Профинструмент', hint: 'Рабочее место инспектора: плотный список, горячие клавиши' },
  { id: 'gos', title: 'Базовая', hint: 'Палитра Госуслуг, первый вариант' },
];

const DARK_THEMES: ThemeId[] = ['dispatch', 'pro'];
const STORAGE_KEY = 'chisto.stand.v1';

interface StandState {
  theme: ThemeId;
  dataset: DatasetId;
  setTheme: (theme: ThemeId) => void;
  setDataset: (dataset: DatasetId) => void;
}

function isTheme(value: unknown): value is ThemeId {
  return THEMES.some((t) => t.id === value);
}

// Тему можно задать ссылкой: ?t=dossier — удобно отправлять коллегам
function readInitial(): { theme: ThemeId; dataset: DatasetId } {
  let theme: ThemeId = 'dispatch';
  let dataset: DatasetId = 'demo';
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (isTheme(saved.theme)) theme = saved.theme;
    if (saved.dataset === 'mock' || saved.dataset === 'demo') dataset = saved.dataset;
  } catch {
    /* хранилище недоступно — берём значения по умолчанию */
  }
  const fromUrl = new URLSearchParams(window.location.search).get('t');
  if (isTheme(fromUrl)) theme = fromUrl;
  return { theme, dataset };
}

function persist(state: { theme: ThemeId; dataset: DatasetId }) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* не критично */
  }
}

export function applyTheme(theme: ThemeId) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle('dark', DARK_THEMES.includes(theme));
  root.style.colorScheme = DARK_THEMES.includes(theme) ? 'dark' : 'light';
}

const initial = readInitial();
applyTheme(initial.theme);

export const useStandStore = create<StandState>((set, get) => ({
  ...initial,
  setTheme: (theme) => {
    applyTheme(theme);
    const url = new URL(window.location.href);
    url.searchParams.set('t', theme);
    window.history.replaceState(null, '', url);
    set({ theme });
    persist({ theme, dataset: get().dataset });
  },
  setDataset: (dataset) => {
    set({ dataset });
    persist({ theme: get().theme, dataset });
  },
}));

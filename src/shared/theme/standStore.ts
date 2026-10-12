import { create } from 'zustand';

// Демонстрационный стенд: три направления дизайна и базовая гос-тема.
// Тема живёт в атрибуте data-theme на <html> — от него зависят токены в themes.css.
export type ThemeId = 'dispatch' | 'dossier' | 'pro' | 'gos';
export type DatasetId = 'demo' | 'mock';
export type ModeId = 'dark' | 'light';

export const THEMES: { id: ThemeId; title: string; hint: string }[] = [
  { id: 'dispatch', title: 'Диспетчерская', hint: 'Ситуационный центр: карта на весь экран, тёмная тема' },
  { id: 'dossier', title: 'Досье', hint: 'Сводка в газетной манере: бумага, засечки, служебная записка' },
  { id: 'pro', title: 'Профинструмент', hint: 'Рабочее место инспектора: плотный список, горячие клавиши' },
  { id: 'gos', title: 'Базовая', hint: 'Палитра Госуслуг, первый вариант' },
];

// Тёмные по замыслу темы; у них есть светлый вариант (mode), остальные всегда светлые
export const MODE_THEMES: ThemeId[] = ['dispatch', 'pro'];
const STORAGE_KEY = 'chisto.stand.v1';

interface StandState {
  theme: ThemeId;
  dataset: DatasetId;
  mode: ModeId;
  setMode: (mode: ModeId) => void;
  setTheme: (theme: ThemeId) => void;
  setDataset: (dataset: DatasetId) => void;
}

function isTheme(value: unknown): value is ThemeId {
  return THEMES.some((t) => t.id === value);
}

// Тему можно задать ссылкой: ?t=dossier — удобно отправлять коллегам
type Saved = { theme: ThemeId; dataset: DatasetId; mode: ModeId };

function readInitial(): Saved {
  let theme: ThemeId = 'dispatch';
  let dataset: DatasetId = 'demo';
  let mode: ModeId = 'dark';
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (isTheme(saved.theme)) theme = saved.theme;
    if (saved.dataset === 'mock' || saved.dataset === 'demo') dataset = saved.dataset;
    if (saved.mode === 'light' || saved.mode === 'dark') mode = saved.mode;
  } catch {
    /* хранилище недоступно — берём значения по умолчанию */
  }
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('t');
  if (isTheme(fromUrl)) theme = fromUrl;
  // ?m=light — светлый вариант «Диспетчерской» и «Профинструмента»
  const modeUrl = params.get('m');
  if (modeUrl === 'light' || modeUrl === 'dark') mode = modeUrl;
  return { theme, dataset, mode };
}

function persist(state: Saved) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* не критично */
  }
}

export function isDark(theme: ThemeId, mode: ModeId): boolean {
  return MODE_THEMES.includes(theme) && mode === 'dark';
}

export function applyTheme(theme: ThemeId, mode: ModeId) {
  const root = document.documentElement;
  const dark = isDark(theme, mode);
  root.dataset.theme = theme;
  root.dataset.mode = dark ? 'dark' : 'light';
  root.classList.toggle('dark', dark);
  root.style.colorScheme = dark ? 'dark' : 'light';
}

function writeUrl(theme: ThemeId, mode: ModeId) {
  const url = new URL(window.location.href);
  url.searchParams.set('t', theme);
  if (MODE_THEMES.includes(theme) && mode === 'light') url.searchParams.set('m', 'light');
  else url.searchParams.delete('m');
  window.history.replaceState(null, '', url);
}

const initial = readInitial();
applyTheme(initial.theme, initial.mode);

export const useStandStore = create<StandState>((set, get) => ({
  ...initial,
  setTheme: (theme) => {
    const { mode, dataset } = get();
    applyTheme(theme, mode);
    writeUrl(theme, mode);
    set({ theme });
    persist({ theme, dataset, mode });
  },
  setMode: (mode) => {
    const { theme, dataset } = get();
    applyTheme(theme, mode);
    writeUrl(theme, mode);
    set({ mode });
    persist({ theme, dataset, mode });
  },
  setDataset: (dataset) => {
    const { theme, mode } = get();
    set({ dataset });
    persist({ theme, dataset, mode });
  },
}));

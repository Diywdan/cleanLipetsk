import { create } from 'zustand';

// Демонстрационный стенд. Дизайн один — «Диспетчерская», у него два тона:
// тёмный (ситуационный центр) и светлый (дневной зал, проектор).
// Тон живёт в атрибуте data-mode на <html> — от него зависят токены в themes.css.
export type DatasetId = 'demo' | 'mock';
export type ModeId = 'dark' | 'light';

const STORAGE_KEY = 'chisto.stand.v2';

interface StandState {
  dataset: DatasetId;
  mode: ModeId;
  setMode: (mode: ModeId) => void;
  setDataset: (dataset: DatasetId) => void;
}

type Saved = { dataset: DatasetId; mode: ModeId };

// Тон можно задать ссылкой: ?m=light — удобно отправлять коллегам
function readInitial(): Saved {
  let dataset: DatasetId = 'demo';
  let mode: ModeId = 'dark';
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (saved.dataset === 'mock' || saved.dataset === 'demo') dataset = saved.dataset;
    if (saved.mode === 'light' || saved.mode === 'dark') mode = saved.mode;
  } catch {
    /* хранилище недоступно — берём значения по умолчанию */
  }
  const fromUrl = new URLSearchParams(window.location.search).get('m');
  if (fromUrl === 'light' || fromUrl === 'dark') mode = fromUrl;
  return { dataset, mode };
}

function persist(state: Saved) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* не критично */
  }
}

export function applyMode(mode: ModeId) {
  const root = document.documentElement;
  root.dataset.mode = mode;
  root.classList.toggle('dark', mode === 'dark');
  root.style.colorScheme = mode;
}

function writeUrl(mode: ModeId) {
  const url = new URL(window.location.href);
  if (mode === 'light') url.searchParams.set('m', 'light');
  else url.searchParams.delete('m');
  window.history.replaceState(null, '', url);
}

const initial = readInitial();
applyMode(initial.mode);

export const useStandStore = create<StandState>((set, get) => ({
  ...initial,
  setMode: (mode) => {
    applyMode(mode);
    writeUrl(mode);
    set({ mode });
    persist({ dataset: get().dataset, mode });
  },
  setDataset: (dataset) => {
    set({ dataset });
    persist({ dataset, mode: get().mode });
  },
}));

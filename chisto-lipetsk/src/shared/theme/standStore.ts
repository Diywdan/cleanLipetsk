import { create } from 'zustand';

// Демонстрационный стенд. Дизайн один — «Диспетчерская», у него три тона:
// тёмный (ситуационный центр), светлый (дневной зал, проектор) и «стекло» —
// вариант на пробу: тёплая вечерняя карта под матовыми панелями.
// Тон живёт в атрибуте data-mode на <html> — от него зависят токены в themes.css.
export type DatasetId = 'demo' | 'mock';
export type ModeId = 'dark' | 'light' | 'glass';
const MODE_IDS: ModeId[] = ['dark', 'light', 'glass'];
const isMode = (v: unknown): v is ModeId => MODE_IDS.includes(v as ModeId);

const STORAGE_KEY = 'chisto.stand.v2';

interface StandState {
  dataset: DatasetId;
  mode: ModeId;
  setMode: (mode: ModeId) => void;
  setDataset: (dataset: DatasetId) => void;
}

type Saved = { dataset: DatasetId; mode: ModeId };

// Тон можно задать ссылкой: ?m=light или ?m=glass — удобно отправлять коллегам
function readInitial(): Saved {
  let dataset: DatasetId = 'demo';
  let mode: ModeId = 'dark';
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (saved.dataset === 'mock' || saved.dataset === 'demo') dataset = saved.dataset;
    if (isMode(saved.mode)) mode = saved.mode;
  } catch {
    /* хранилище недоступно — берём значения по умолчанию */
  }
  const fromUrl = new URLSearchParams(window.location.search).get('m');
  if (isMode(fromUrl)) mode = fromUrl;
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
  // «Стекло» — светлый текст на затемнённых панелях, поэтому для shadcn это тёмная тема
  root.classList.toggle('dark', mode !== 'light');
  root.style.colorScheme = mode === 'light' ? 'light' : 'dark';
}

function writeUrl(mode: ModeId) {
  const url = new URL(window.location.href);
  if (mode !== 'dark') url.searchParams.set('m', mode);
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

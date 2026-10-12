import { create } from 'zustand';
import type { IKpCard } from '../types';
import type { KpApi } from './kpApi';

interface KpStore {
  cards: IKpCard[];
  error: string | null;
  load: (api: KpApi) => Promise<void>;
}

export const useKpStore = create<KpStore>((set) => ({
  cards: [],
  error: null,
  load: async (api) => {
    try {
      set({ cards: await api.list(), error: null });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Не удалось загрузить справочник КП' });
    }
  },
}));

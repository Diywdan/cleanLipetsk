import { create } from 'zustand';
import type { IExecutorRef } from '../types';
import type { ExecutorApi } from './executorApi';

interface ExecutorStore {
  executors: IExecutorRef[];
  load: (api: ExecutorApi) => Promise<void>;
}

export const useExecutorStore = create<ExecutorStore>((set) => ({
  executors: [],
  load: async (api) => {
    try {
      set({ executors: await api.list() });
    } catch {
      // Справочник не дали (нет прав или нет связи) — выбор исполнителя просто не показывается
      set({ executors: [] });
    }
  },
}));

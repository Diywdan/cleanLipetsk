import { create } from 'zustand';
import type { IDocumentServiceData, IIncident, IPhotoReport } from '../types';
import type { DeadlineHours } from '../lib/sla';
import type { ActionPayload, Actor, IncidentAction } from '../lib/workflow';
import type { IncidentApi } from '../api/incidentApi';
import { useAuthStore } from '@/entities/user/model/authStore';

// Состояние интерфейса: список обращений и открытое дело. Данные и правила —
// в incidentApi и lib/workflow; стор только вызывает их и раскладывает результат.

interface IncidentStore {
  incidents: IIncident[];
  selectedIncident: IIncident | null;
  isLoading: boolean;
  error: string | null;        // последняя ошибка действия — показывается в карточке
  persistent: boolean;         // сохраняются ли изменения между перезагрузками
  api: IncidentApi | null;

  load: (api: IncidentApi, openId?: string | null) => Promise<void>;
  // Тихо перечитать список (новые дела из бота, эскалация сервером) — без индикатора загрузки
  refresh: () => Promise<void>;
  resetDemo: () => Promise<void>;
  selectIncident: (id: string | null) => void;
  clearError: () => void;

  // Маршрут дела (правила — lib/workflow.ts)
  confirmIncident: (id: string, deadlineHours: DeadlineHours, reassign?: { executorId?: string; typeViolationId?: string }) => Promise<void>;
  dismissIncident: (id: string, reason?: string) => Promise<void>;
  submitPhotoReport: (id: string, report: IPhotoReport) => Promise<void>;
  approveIncident: (id: string) => Promise<void>;
  returnIncident: (id: string, comment?: string) => Promise<void>;
  // auto — по таймеру срока (автор — система), иначе вручную инспектором
  triggerKnmEscalation: (id: string, auto?: boolean) => Promise<void>;
  issueKnmAct: (id: string) => Promise<void>;
  syncDocuments: (id: string) => Promise<boolean>;
  saveDocumentServiceData: (id: string, data: IDocumentServiceData) => Promise<boolean>;
}

function currentActor(): Actor {
  const user = useAuthStore.getState().currentUser;
  if (!user) throw new Error('Нет пользователя');
  return { kind: 'USER', role: user.role, name: user.name, organizationName: user.organizationName };
}

export const useIncidentStore = create<IncidentStore>((set, get) => {
  async function run<A extends IncidentAction>(id: string, action: A, payload: ActionPayload[A], actor?: Actor) {
    const api = get().api;
    if (!api) return;
    try {
      const updated = await api.act(id, action, payload, actor ?? currentActor());
      set((state) => ({
        incidents: state.incidents.map((i) => (i.id === id ? updated : i)),
        selectedIncident: state.selectedIncident?.id === id ? updated : state.selectedIncident,
        persistent: api.persistent,
        error: null,
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Не удалось выполнить действие' });
    }
  }

  return {
    incidents: [],
    selectedIncident: null,
    isLoading: false,
    error: null,
    persistent: true,
    api: null,

    load: async (api, openId) => {
      set({ isLoading: true, api, error: null });
      try {
        const incidents = await api.list();
        const keepId = openId ?? get().selectedIncident?.id ?? null;
        set({
          incidents,
          selectedIncident: keepId ? incidents.find((i) => i.id === keepId) ?? null : null,
          persistent: api.persistent,
          isLoading: false,
        });
      } catch (e) {
        set({ isLoading: false, error: e instanceof Error ? e.message : 'Не удалось загрузить обращения' });
      }
    },

    refresh: async () => {
      const api = get().api;
      if (!api) return;
      try {
        const incidents = await api.list();
        set((state) => ({
          incidents,
          selectedIncident: state.selectedIncident
            ? incidents.find((i) => i.id === state.selectedIncident?.id) ?? null
            : null,
        }));
      } catch {
        /* сеть моргнула — обновимся в следующий раз */
      }
    },

    resetDemo: async () => {
      const api = get().api;
      if (!api?.reset) return;
      const incidents = await api.reset();
      set({ incidents, selectedIncident: null, error: null, persistent: api.persistent });
    },

    selectIncident: (id) =>
      set((state) => ({
        selectedIncident: id ? state.incidents.find((inc) => inc.id === id) ?? null : null,
        error: null,
      })),

    clearError: () => set({ error: null }),

    confirmIncident: (id, deadlineHours, reassign) => run(id, 'CONFIRM', { deadlineHours, ...reassign }),
    dismissIncident: (id, reason) => run(id, 'DISMISS', { reason }),
    submitPhotoReport: (id, report) => run(id, 'SUBMIT_REPORT', { report }),
    approveIncident: (id) => run(id, 'APPROVE', {}),
    returnIncident: (id, comment) => run(id, 'RETURN', { comment }),
    triggerKnmEscalation: (id, auto = true) => run(id, 'ESCALATE', {}, auto ? { kind: 'SYSTEM' } : undefined),
    issueKnmAct: (id) => run(id, 'ISSUE_ACT', {}),
    syncDocuments: async (id) => {
      const api = get().api;
      if (!api) return false;
      try {
        const updated = await api.syncDocuments(id);
        set((state) => ({
          incidents: state.incidents.map((i) => (i.id === id ? updated : i)),
          selectedIncident: state.selectedIncident?.id === id ? updated : state.selectedIncident,
          error: null,
        }));
        return true;
      } catch (e) {
        set({ error: e instanceof Error ? e.message : 'Не удалось обновить статус документов' });
        return false;
      }
    },
    saveDocumentServiceData: async (id, data) => {
      const api = get().api;
      if (!api) return false;
      try {
        const updated = await api.saveDocumentServiceData(id, data);
        set((state) => ({
          incidents: state.incidents.map((i) => (i.id === id ? updated : i)),
          selectedIncident: state.selectedIncident?.id === id ? updated : state.selectedIncident,
          error: null,
        }));
        return true;
      } catch (e) {
        set({ error: e instanceof Error ? e.message : 'Не удалось сохранить данные документов' });
        return false;
      }
    },
  };
});

import { create } from 'zustand';
import { type IIncident, type IncidentStatus } from '../types';
import { resolveDeadlineHours, type DeadlineHours } from '../lib/sla';

// Описываем интерфейс нашего хранилища
interface IncidentStore {
  // Состояние (State)
  incidents: IIncident[];              // Массив всех инцидентов для отображения на гео-карте
  selectedIncident: IIncident | null;  // Инцидент, открытый в "едином окне" прямо сейчас
  isLoading: boolean;

  // Действия (Actions)
  setIncidents: (incidents: IIncident[]) => void;
  selectIncident: (id: string | null) => void;
  
  // Экшены переходов по Маршрутной карте (State Machine)
  confirmIncident: (id: string, deadlineHours: DeadlineHours) => void; // Шаг 6: Уведомить владельца
  submitPhotoReport: (id: string, photoAfterUrl: string) => void;     // Шаг 7: УК отчиталась
  approveIncident: (id: string) => void;                              // Шаг 8: Закрыть (Устранено)
  rejectIncident: (id: string) => void;                               // Возврат на доработку в УК
  triggerKnmEscalation: (id: string) => void;                         // Шаг 8: Эскалация в КНМ (Срок истёк)
}

export const useIncidentStore = create<IncidentStore>((set) => ({
  // Начальное состояние
  incidents: [],
  selectedIncident: null,
  isLoading: false,

  setIncidents: (incidents) => set({ incidents }),

  // Выбор точки на карте для открытия в "едином окне"
  selectIncident: (id) => set((state) => ({
    selectedIncident: id ? state.incidents.find((inc) => inc.id === id) || null : null
  })),

  // Шаг 1: Инспектор подтверждает нарушение и запускает таймер для УК (Шаг 6 по регламенту).
  // Срок берётся из матрицы SLA: для части источников он фиксирован, иначе — выбор инспектора.
  confirmIncident: (id, deadlineHours) => set((state) => {
    const now = new Date();
    const target = state.incidents.find((inc) => inc.id === id);
    const hours = target ? resolveDeadlineHours(target.source, deadlineHours) : deadlineHours;
    const deadline = new Date(now.getTime() + hours * 60 * 60 * 1000);

    const updatedIncidents = state.incidents.map((inc) => {
      if (inc.id !== id) return inc;
      return {
        ...inc,
        status: 'IN_PROGRESS' as IncidentStatus,
        timeline: {
          ...inc.timeline,
          validatedAt: now.toISOString(),
          deadlineAt: deadline.toISOString(),
        }
      };
    });

    return {
      incidents: updatedIncidents,
      // Если карточка открыта в едином окне — обновляем и её
      selectedIncident: state.selectedIncident?.id === id 
        ? updatedIncidents.find((inc) => inc.id === id) || null 
        : state.selectedIncident
    };
  }),

  // Шаг 2: Мастер УК загружает фотоотчет "Стало" (Шаг 7 по регламенту)
  submitPhotoReport: (id, photoAfterUrl) => set((state) => {
    const updatedIncidents = state.incidents.map((inc) => {
      if (inc.id !== id) return inc;
      return {
        ...inc,
        status: 'VERIFICATION' as IncidentStatus,
        media: {
          ...inc.media,
          photoAfterUrl
        }
      };
    });

    return {
      incidents: updatedIncidents,
      selectedIncident: state.selectedIncident?.id === id 
        ? updatedIncidents.find((inc) => inc.id === id) || null 
        : state.selectedIncident
    };
  }),

  // Шаг 3А: Инспектор одобряет уборку двора — дело успешно закрыто
  approveIncident: (id) => set((state) => {
    const updatedIncidents = state.incidents.map((inc) => {
      if (inc.id !== id) return inc;
      return {
        ...inc,
        status: 'CLOSED' as IncidentStatus,
        timeline: {
          ...inc.timeline,
          closedAt: new Date().toISOString()
        }
      };
    });

    return {
      incidents: updatedIncidents,
      selectedIncident: state.selectedIncident?.id === id 
        ? updatedIncidents.find((inc) => inc.id === id) || null 
        : state.selectedIncident
    };
  }),

  // Шаг 3Б: Мусор убран плохо — инспектор возвращает карточку обратно в УК
  rejectIncident: (id) => set((state) => {
    const updatedIncidents = state.incidents.map((inc) => {
      if (inc.id !== id) return inc;
      return {
        ...inc,
        status: 'IN_PROGRESS' as IncidentStatus, // Возвращаем статус, но дедлайн НЕ сбрасывается!
      };
    });

    return {
      incidents: updatedIncidents,
      selectedIncident: state.selectedIncident?.id === id 
        ? updatedIncidents.find((inc) => inc.id === id) || null 
        : state.selectedIncident
    };
  }),

  // РЕЗЕРВНЫЙ СЦЕНАРИЙ: Время вышло, автоматический или ручной перевод в КНМ-контур для штрафов
  triggerKnmEscalation: (id) => set((state) => {
    const updatedIncidents = state.incidents.map((inc) => {
      if (inc.id !== id) return inc;
      return {
        ...inc,
        status: 'KNM_ESCALATION' as IncidentStatus
      };
    });

    return {
      incidents: updatedIncidents,
      selectedIncident: state.selectedIncident?.id === id 
        ? updatedIncidents.find((inc) => inc.id === id) || null 
        : state.selectedIncident
    };
  })
}));

import { create } from 'zustand';
import { type IIncident, type IncidentStatus } from '../types';

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
  confirmIncident: (id: string, deadlineHours: 24 | 48 | 72 | 720) => void; // Шаг 6: Уведомить владельца
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

  // Шаг 1: Инспектор подтверждает нарушение и запускает таймер для УК (Шаг 6 по регламенту)
  confirmIncident: (id, deadlineHours) => set((state) => {
    const now = new Date();

      // Находим текущий инцидент в массиве, чтобы посмотреть его источник (source)
    const targetIncident = state.incidents.find((inc) => inc.id === id);
    
    // Значение по умолчанию — то, что инспектор выбрал руками на панели (24, 48 или 72ч)
    let hoursToResolve = deadlineHours;

    if (targetIncident) {
      // АВТОМАТИЧЕСКАЯ МАТРИЦА SLA СОГЛАСНО РЕГЛАМЕНТУ ДРТ
      if (targetIncident.source === 'DIRECT_ORDER') {
        hoursToResolve = 24; // Личное указание руководства — строго 1 день [1]
      } else if (targetIncident.source === 'GOVERNOR_PORTAL') {
        hoursToResolve = 72; // Портал губернатора — строго 3 дня [1]
      } else if (targetIncident.source === 'DELO_WEB') {
        hoursToResolve = 720; // Официальный контур Дело-web — норматив до 30 дней [1]
      }
    }

    const deadline = new Date();
    deadline.setHours(now.getHours() + deadlineHours); // Динамический расчет дедлайна (24-72ч)

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

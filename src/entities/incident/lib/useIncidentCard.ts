import { useState } from 'react';
import { useIncidentStore } from '../model/incidentStore';
import { useIncidentTimer } from './useIncidentTimer';

export function useIncidentCard() {
  // 1. Достаем из Zustand-стора текущий выбранный инцидент и экшены маршрутной карты
  const {
    selectedIncident,
    confirmIncident,
    submitPhotoReport,
    approveIncident,
    rejectIncident,
  } = useIncidentStore();

  // 2. Локальные стейты для управления формами и слоями нейросети внутри карточки
  const [selectedDeadline, setSelectedDeadline] = useState<24 | 48 | 72>(48);
  const [showAiLayer, setShowAiLayer] = useState<boolean>(true);

  // 3. Подключаем тикающий SLA-таймер обратного отсчета (если инцидент выбран)
  const timer = useIncidentTimer(
    selectedIncident?.id || '',
    selectedIncident?.timeline.deadlineAt,
    selectedIncident?.status
  );

  // Срок по матрице SLA применяет стор (lib/sla.ts) — здесь только передаём выбор инспектора
  const handleConfirm = () => {
    if (!selectedIncident) return;
    confirmIncident(selectedIncident.id, selectedDeadline);
  };

  return {
    selectedIncident,
    confirmIncident: handleConfirm,
    submitPhotoReport,
    approveIncident,
    rejectIncident,
    selectedDeadline,
    setSelectedDeadline,
    showAiLayer,
    setShowAiLayer,
    formattedTime: timer.formattedTime,
    isExpired: timer.isExpired,
    slalabel: timer.slaLabel
  };
}

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

  // Карточка сама решает, какую цифру отправить в стор, избавляя нас от useEffect лагов!
  const handleConfirm = () => {
    if (!selectedIncident) return;

    let finalHours: 24 | 48 | 72 | 720 = selectedDeadline;

    // Жесткая проверка ведомственного регламента Липецка перед отправкой в Zustand
    if (selectedIncident.source === 'DIRECT_ORDER') {
      finalHours = 24;      // Начальство — строго сутки [1]
    } else if (selectedIncident.source === 'GOVERNOR_PORTAL') {
      finalHours = 72;      // Губернатор — строго 3 дня [1]
    } else if (selectedIncident.source === 'DELO_WEB') {
      finalHours = 720;     // Дело-web — строго 30 дней [1]
    }

    // Отправляем в стор гарантированно правильную цифру
    confirmIncident(selectedIncident.id, finalHours);
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

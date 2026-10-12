import type { IIncident } from '../../types';
import { SOURCE_TITLE, formatDateTime } from '../../lib/presentation';
import { useIncidentCard } from '../../lib/useIncidentCard';
import { useIncidentStore } from '../../model/incidentStore';
import { getPrimaryResponsible } from '../../lib/responsibles';
import type { CardActionHandlers } from './parts';
import afterPhoto from '@/assets/demo/kp-after.svg';

// Доля прошедшего срока: от подтверждения до дедлайна
export function slaShare(incident: IIncident, msLeft: number): number {
  const { validatedAt, deadlineAt } = incident.timeline;
  if (!validatedAt || !deadlineAt) return 0;
  const total = new Date(deadlineAt).getTime() - new Date(validatedAt).getTime();
  if (total <= 0) return 1;
  return Math.min(1, Math.max(0, 1 - msLeft / total));
}

export const sourceLine = (incident: IIncident) =>
  `${SOURCE_TITLE[incident.source] ?? incident.source} · ${formatDateTime(incident.timeline.createdAt)}`;

// Всё, что нужно оболочке карточки: выбранное обращение, таймер, обработчики
export function useCardModel() {
  const card = useIncidentCard();
  const close = useIncidentStore((s) => s.selectIncident);
  const incident = card.selectedIncident;

  const handlers: CardActionHandlers = {
    confirmIncident: card.confirmIncident,
    rejectIncident: card.rejectIncident,
    approveIncident: card.approveIncident,
    submitPhotoReport: card.submitPhotoReport,
    selectedDeadline: card.selectedDeadline,
    setSelectedDeadline: card.setSelectedDeadline,
    afterPhoto,
  };

  return {
    incident,
    primary: incident ? getPrimaryResponsible(incident) : undefined,
    showAi: card.showAiLayer,
    setShowAi: card.setShowAiLayer,
    sla: {
      formattedTime: card.formattedTime,
      msLeft: card.msLeft,
      isExpired: card.isExpired,
      label: card.slalabel,
      active: Boolean(incident?.timeline.deadlineAt && incident.status === 'IN_PROGRESS'),
    },
    handlers,
    close: () => close(null),
  };
}

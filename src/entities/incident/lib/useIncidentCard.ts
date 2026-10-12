import { useState } from 'react';
import { useIncidentStore } from '../model/incidentStore';
import { useIncidentTimer } from './useIncidentTimer';

// Открытое дело, слой разметки ИИ и тикающий срок. Действия по делу — в ui/card/CardActions.
export function useIncidentCard() {
  const selectedIncident = useIncidentStore((s) => s.selectedIncident);
  const [showAiLayer, setShowAiLayer] = useState<boolean>(true);

  const timer = useIncidentTimer(
    selectedIncident?.id || '',
    selectedIncident?.timeline.deadlineAt,
    selectedIncident?.status,
  );

  return {
    selectedIncident,
    showAiLayer,
    setShowAiLayer,
    formattedTime: timer.formattedTime,
    msLeft: timer.msLeft,
    isExpired: timer.isExpired,
    slalabel: timer.slaLabel,
  };
}

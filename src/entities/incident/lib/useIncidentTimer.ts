import { useEffect, useState } from 'react';
import { useIncidentStore } from '../model/incidentStore';

interface UseIncidentTimerResult {
  formattedTime: string; // Строка вида "23:59:45" или "Срок истёк"
  msLeft: number;        // Сколько осталось, мс (0 — срок вышел)
  isExpired: boolean;    // Флаг просрочки для смены стилей UI
  slaLabel: string;
}

/**
 * Кастомный хук для обратного отсчета времени SLA (24-72 часа)
 * Автоматически эскалирует дело в КНМ при достижении нуля
 */
export function useIncidentTimer(incidentId: string, deadlineAt?: string, status?: string): UseIncidentTimerResult {
  const triggerKnmEscalation = useIncidentStore((state) => state.triggerKnmEscalation);
  const selectedIncident = useIncidentStore((state) => state.selectedIncident);
  // Если дедлайна нет или инцидент уже закрыт/эскалирован — таймер не нужен
  const active = !!deadlineAt && status !== 'CLOSED' && status !== 'KNM_ESCALATION';
  const deadlineMs = deadlineAt ? new Date(deadlineAt).getTime() : 0;
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    if (!active) return;

    const tick = () => {
      const t = Date.now();
      setNow(t);
      // КРИТИЧЕСКИЙ СЦЕНАРИЙ: время вышло — авто-перевод в надзорный контур ГЖИ Липецка
      if (deadlineMs - t <= 0) {
        triggerKnmEscalation(incidentId);
        return true;
      }
      return false;
    };

    // Ежесекундный тик; первый — сразу, без ожидания
    const first = setTimeout(tick, 0);
    const intervalId = setInterval(() => {
      if (tick()) clearInterval(intervalId);
    }, 1000);

    // Очистка при переключении карточек или закрытии окон
    return () => {
      clearTimeout(first);
      clearInterval(intervalId);
    };
  }, [active, incidentId, deadlineMs, triggerKnmEscalation]);

  const timeLeft = active ? Math.max(0, deadlineMs - now) : 0;

   // ГЕНЕРАЦИЯ ПОДСКАЗОК НА ОСНОВЕ МАТРИЦЫ ИСТОЧНИКОВ И ПРИОРИТЕТОВ ДРТ
  let slaLabel = 'Стандартный срок благоустройства';
  if (selectedIncident?.source === 'DIRECT_ORDER') {
    slaLabel = 'Высший приоритет: поручение руководства, 1 сутки';
  } else if (selectedIncident?.source === 'GOVERNOR_PORTAL') {
    slaLabel = 'Высокий приоритет: портал губернатора, 3 суток';
  } else if (selectedIncident?.source === 'DELO_WEB') {
    slaLabel = 'Письмо через Дело-web: до 30 суток';
  } else if (selectedIncident?.media.boundingBoxes.some((box) => box.label.includes('ТКО') || box.label.includes('КГМ'))) {
    slaLabel = 'Повышенный приоритет: ТКО и КГМ';
  }

  // Вспомогательная функция для превращения миллисекунд в красивую читаемую строку
  const formatTime = (ms: number): string => {
    if (ms <= 0) return 'Срок истёк';

    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    // Добавляем ведущие нули (например, "05:09:02")
    const pad = (num: number) => String(num).padStart(2, '0');

    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  };

  return {
    formattedTime: formatTime(timeLeft),
    msLeft: timeLeft,
    isExpired: timeLeft <= 0 && !!deadlineAt && status !== 'CLOSED',
    slaLabel
  };
}

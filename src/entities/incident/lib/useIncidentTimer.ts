import { useEffect, useState } from 'react';
import { useIncidentStore } from '../model/incidentStore';

interface UseIncidentTimerResult {
  formattedTime: string; // Строка вида "23:59:45" или "СРОК ИСТЕК"
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
  const [timeLeft, setTimeLeft] = useState<number>(0);

  useEffect(() => {
    // Если дедлайна нет или инцидент уже закрыт/эскалирован — таймер не нужен
    if (!deadlineAt || status === 'CLOSED' || status === 'KNM_ESCALATION') {
      setTimeLeft(0);
      return;
    }

    const calculateTimeLeft = () => {
      const difference = new Date(deadlineAt).getTime() - Date.now();
      
      // КРИТИЧЕСКИЙ СЦЕНАРИЙ: Таймер дошел до нуля, время вышло!
      if (difference <= 0) {
        setTimeLeft(0);
        triggerKnmEscalation(incidentId); // Авто-перевод в надзорный контур ГЖИ Липецка
        return true; // Возвращаем true, чтобы остановить интервал
      }

      setTimeLeft(difference);
      return false;
    };

    // Первичный расчет при монтировании инцидента в "Единое окно"
    const isOver = calculateTimeLeft();
    if (isOver) return;

    // Запускаем ежесекундный тик таймера дедлайна
    const intervalId = setInterval(() => {
      const isOverTick = calculateTimeLeft();
      if (isOverTick) {
        clearInterval(intervalId);
      }
    }, 1000);

    // Очистка интервала при переключении карточек или закрытии окон
    return () => clearInterval(intervalId);
  }, [incidentId, deadlineAt, status, triggerKnmEscalation]);

   // ГЕНЕРАЦИЯ ПОДСКАЗОК НА ОСНОВЕ МАТРИЦЫ ИСТОЧНИКОВ И ПРИОРИТЕТОВ ДРТ
  let slaLabel = 'Стандартный срок благоустройства';
  if (selectedIncident?.source === 'DIRECT_ORDER') {
    slaLabel = 'Высший приоритет: поручение руководства, 1 сутки';
  } else if (selectedIncident?.source === 'GOVERNOR_PORTAL') {
    slaLabel = 'Высокий приоритет: портал губернатора, 3 суток';
  } else if (selectedIncident?.source === 'DELO_WEB') {
    slaLabel = 'Письмо через Дело-web: до 30 суток';
  } else if (selectedIncident?.media.boundingBoxes.some((box: any) => box.label.includes('ТКО') || box.label.includes('КГМ'))) {
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
    isExpired: timeLeft <= 0 && !!deadlineAt && status !== 'CLOSED',
    slaLabel
  };
}

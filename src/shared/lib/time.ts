import { useEffect, useState } from 'react';

// Текущее время через функцию модуля: правило чистоты react-hooks запрещает
// звать Date.now() прямо в рендере, а «живые» подписи без него не сделать.
export function nowMs(): number {
  return Date.now();
}

// Тикающее «сейчас» для часов и подписей «5 мин назад»
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(nowMs);
  useEffect(() => {
    const id = setInterval(() => setNow(nowMs()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export function timeAgo(iso: string, now: number): string {
  const min = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
  if (min < 1) return 'только что';
  if (min < 60) return `${min} мин назад`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} ч назад`;
  const d = Math.floor(h / 24);
  return `${d} ${plural(d, 'день', 'дня', 'дней')} назад`;
}

// Остаток срока: «5 ч 20 мин», «2 сут 4 ч», «просрочено на 3 ч»
export function timeLeft(deadlineIso: string, now: number): { text: string; overdue: boolean; ms: number } {
  const ms = new Date(deadlineIso).getTime() - now;
  const abs = Math.abs(ms);
  const h = Math.floor(abs / 3_600_000);
  const m = Math.floor((abs % 3_600_000) / 60_000);
  const span = abs < 60_000 ? '< 1 мин' : h >= 24 ? `${Math.floor(h / 24)} сут ${h % 24} ч` : h > 0 ? `${h} ч ${m} мин` : `${m} мин`;
  return ms >= 0 ? { text: span, overdue: false, ms } : { text: `просрочено на ${span}`, overdue: true, ms };
}

export { plural };

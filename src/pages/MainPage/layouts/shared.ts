import { useCallback, useState } from 'react';
import type { UserRole } from '@/entities/user/types';

// Общее для раскладок тем: разделы, подписи ролей, инициалы, номер выпуска.

export type AppTab = 'map_view' | 'analytics' | 'kp';

export const ROLE_TITLE: Record<UserRole, string> = {
  INSPECTOR: 'Инспектор ДРТ',
  UK: 'Исполнитель',
  ADMIN: 'Руководство',
};

export function initials(name: string): string {
  return name
    .replace(/\(.*?\)/g, '')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();
}

// Номер выпуска «Досье» — день года: у каждой сводки свой номер
export function issueNumber(now: number): number {
  const d = new Date(now);
  const start = new Date(d.getFullYear(), 0, 0).getTime();
  return Math.floor((d.getTime() - start) / 86_400_000);
}


// Раздел живёт в адресе (?v=analytics), чтобы ссылкой можно было открыть сразу аналитику
export function useUrlState<T extends string>(fallback: T, allowed: readonly T[]): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('v') as T | null;
    return fromUrl && allowed.includes(fromUrl) ? fromUrl : fallback;
  });
  const set = useCallback(
    (next: T) => {
      const url = new URL(window.location.href);
      if (next === fallback) url.searchParams.delete('v');
      else url.searchParams.set('v', next);
      window.history.replaceState(null, '', url);
      setValue(next);
    },
    [fallback],
  );
  return [value, set];
}

export const APP_TABS = ['map_view', 'analytics', 'kp'] as const;

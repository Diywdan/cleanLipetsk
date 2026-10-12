import { useMemo } from 'react';
import { useStandStore } from './standStore';

// Цвета для мест, куда CSS-переменную не передать (SVG графиков, полигоны карты).
// applyTheme меняет data-theme синхронно до рендера, поэтому computed style уже новый.
export function readCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const NAMES = [
  'background', 'foreground', 'card', 'muted', 'muted-foreground', 'border', 'primary',
  'st-new', 'st-work', 'st-check', 'st-knm', 'st-done',
  'chart-grid', 'chart-axis', 'chart-1', 'chart-2', 'zone-1', 'zone-2',
] as const;

export type ThemeColors = Record<(typeof NAMES)[number], string>;

export function readThemeColors(): ThemeColors {
  const out = {} as ThemeColors;
  for (const name of NAMES) out[name] = readCssVar(`--${name}`);
  return out;
}

export function useThemeColors(): ThemeColors {
  const theme = useStandStore((s) => s.theme);
  // theme нужен как ключ пересчёта: значения читаются из DOM
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => readThemeColors(), [theme]);
}

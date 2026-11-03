// Браузерное хранилище для демо-стенда. В приватном окне, при заблокированных
// данных сайта или переполнении localStorage бросает — стенд должен работать и так.

export function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

// false — не сохранилось (нет места, запрещено); вызывающий решает, говорить ли об этом
export function writeJson(key: string, value: unknown): boolean {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function removeKey(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* не критично */
  }
}

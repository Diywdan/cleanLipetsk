// Тонкая обёртка над fetch для бэкенда (VITE_API_URL — CRM «Чистый Липецк»).
// Авторизация — кука сессии CRM (credentials: 'include'), токенов во фронте нет.

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// Сессия истекла или пользователя отключили — authStore возвращает на экран входа
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export async function http<T>(baseUrl: string, path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
    method: init?.method ?? 'GET',
    credentials: 'include',
    headers: init?.body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (res.status === 401 && onUnauthorized) onUnauthorized();
  if (!res.ok) {
    // Ошибка бэкенда: { "message": "..." }; иначе — текст статуса
    let message = res.statusText;
    try {
      const body = (await res.json()) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(res.status, message);
  }
  // Вход и выход отвечают 204 без тела
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const API_URL: string | undefined = import.meta.env.VITE_API_URL || undefined;

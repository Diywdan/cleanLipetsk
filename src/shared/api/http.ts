// Тонкая обёртка над fetch для будущего бэкенда (VITE_API_URL).
// Авторизация — куки сессии Gateway (credentials: 'include'), токенов во фронте нет.

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function http<T>(baseUrl: string, path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
    method: init?.method ?? 'GET',
    credentials: 'include',
    headers: init?.body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
  });
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
  return (await res.json()) as T;
}

export const API_URL: string | undefined = import.meta.env.VITE_API_URL || undefined;

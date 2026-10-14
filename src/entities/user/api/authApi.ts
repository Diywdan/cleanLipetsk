import type { IUser, UserRole } from '../types';
import { http } from '@/shared/api/http';

// Вход в CRM: логин и пароль -> кука сессии; профиль — GET /auth/me.
// Роль и ведомство CRM отдаёт уже в терминах фронта (docs/api-contract.md).

interface MeResponse {
  id: number;
  name: string;
  role: UserRole | null;
  department: string;
  organizationName: string | null;
}

export async function fetchMe(baseUrl: string): Promise<IUser> {
  const me = await http<MeResponse>(baseUrl, '/auth/me');
  if (!me.role) throw new Error('У учётной записи нет доступа к делам. Обратитесь к администратору CRM.');
  return {
    id: String(me.id),
    name: me.name,
    role: me.role,
    department: me.department,
    organizationName: me.organizationName ?? undefined,
  };
}

export function signIn(baseUrl: string, username: string, password: string): Promise<void> {
  return http<void>(baseUrl, '/auth/login', { method: 'POST', body: { username, password } });
}

export function signOut(baseUrl: string): Promise<void> {
  return http<void>(baseUrl, '/auth/logout', { method: 'POST' });
}

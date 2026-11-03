import { create } from 'zustand';
import { type IUser, type UserRole, type LipetskDepartment } from '../types';
import { fetchMe, signIn, signOut } from '../api/authApi';
import { API_URL, ApiError, setUnauthorizedHandler } from '@/shared/api/http';

// checking — спрашиваем CRM, есть ли сессия; anonymous — нужен вход; ready — пользователь известен
export type AuthStatus = 'checking' | 'anonymous' | 'ready';

interface AuthStore {
  // Состояние (State)
  currentUser: IUser | null;
  isAuthenticated: boolean;
  status: AuthStatus;
  error: string | null;

  // Действия (Actions)
  login: (user: IUser) => void;
  logout: () => void;

  // Вход в CRM (VITE_API_URL); на стенде без бэкенда не вызываются
  restore: () => Promise<void>;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;

  // DEV-ACTION: Инструмент для фронтендера, чтобы переключать роли на лету прямо на экране
  switchDevRole: (role: UserRole, department?: LipetskDepartment, orgName?: string) => void;
}

// По умолчанию на стенде сразу авторизуем Инспектора ДРТ Липецка для удобства разработки MVP
const DEV_USER: IUser = {
  id: 'usr_001',
  name: 'Алексей Смирнов',
  role: 'INSPECTOR',
  department: 'DRT'
};

const message = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

export const useAuthStore = create<AuthStore>((set, get) => ({
  // С бэкендом пользователь неизвестен, пока CRM не ответит на /auth/me
  currentUser: API_URL ? null : DEV_USER,
  isAuthenticated: !API_URL,
  status: API_URL ? 'checking' : 'ready',
  error: null,

  login: (user) => set({ currentUser: user, isAuthenticated: true, status: 'ready', error: null }),

  logout: () => set({ currentUser: null, isAuthenticated: false, status: 'anonymous' }),

  restore: async () => {
    if (!API_URL) return;
    try {
      get().login(await fetchMe(API_URL));
    } catch (e) {
      // 401 — просто нет сессии, остальное показываем на экране входа
      set({ currentUser: null, isAuthenticated: false, status: 'anonymous',
            error: e instanceof ApiError && e.status === 401 ? null : message(e, 'CRM недоступна') });
    }
  },

  signIn: async (username, password) => {
    if (!API_URL) return;
    set({ error: null });
    try {
      await signIn(API_URL, username, password);
      get().login(await fetchMe(API_URL));
    } catch (e) {
      set({ error: e instanceof ApiError && e.status === 401 ? 'Неверный логин или пароль' : message(e, 'Не удалось войти') });
    }
  },

  signOut: async () => {
    if (API_URL) {
      try {
        await signOut(API_URL);
      } catch {
        /* сессия и так закончится */
      }
    }
    set({ currentUser: null, isAuthenticated: false, status: 'anonymous', error: null });
  },

  // Функция мгновенной смены роли без перезагрузки страницы
  switchDevRole: (role, department = 'DRT', orgName) => set(() => {
    const devNames: Record<UserRole, string> = {
      INSPECTOR: 'Григорий Петров',
      UK: 'Сергей Козлов',
      ADMIN: 'Ирина Волкова'
    };

    return {
      currentUser: {
        id: `dev_${role.toLowerCase()}`,
        name: devNames[role],
        role,
        department,
        organizationName: orgName
      }
    };
  })
}));

// Любой 401 от CRM посреди работы — сессия кончилась, возвращаемся на вход
setUnauthorizedHandler(() => {
  if (useAuthStore.getState().status === 'ready') {
    useAuthStore.setState({ currentUser: null, isAuthenticated: false, status: 'anonymous',
                            error: 'Сессия закончилась, войдите снова' });
  }
});

import { create } from 'zustand';
import { type IUser, type UserRole, type LipetskDepartment } from '../types';

interface AuthStore {
  // Состояние (State)
  currentUser: IUser | null;
  isAuthenticated: boolean;

  // Действия (Actions)
  login: (user: IUser) => void;
  logout: () => void;
  
  // DEV-ACTION: Инструмент для фронтендера, чтобы переключать роли на лету прямо на экране
  switchDevRole: (role: UserRole, department?: LipetskDepartment, orgName?: string) => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  // По умолчанию сразу авторизуем Инспектора ДРТ Липецка для удобства разработки MVP
  currentUser: {
    id: 'usr_001',
    name: 'Алексей ДРТ',
    role: 'INSPECTOR',
    department: 'DRT'
  },
  isAuthenticated: true,

  login: (user) => set({ currentUser: user, isAuthenticated: true }),
  
  logout: () => set({ currentUser: null, isAuthenticated: false }),

  // Функция мгновенной смены роли без перезагрузки страницы
  switchDevRole: (role, department = 'DRT', orgName) => set(() => {
    const devNames: Record<UserRole, string> = {
      INSPECTOR: 'Григорий (Инспектор ДРТ)',
      UK: 'Сергей (Мастер УК)',
      ADMIN: 'Руководство (ЦУР Липецк)'
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

import type { IKpCard } from '../types';
import { API_URL, http } from '@/shared/api/http';

// Справочник КП. Ведёт его CRM, другие системы читают через Data Gateway;
// интерфейс работает через этот контракт, адрес меняется в одном месте.
export interface KpApi {
  list(): Promise<IKpCard[]>;
}

export function createMockKpApi(cards: () => IKpCard[]): KpApi {
  return { list: async () => cards() };
}

export function createHttpKpApi(baseUrl: string): KpApi {
  return { list: () => http<IKpCard[]>(baseUrl, '/kp') };
}

export function createKpApi(cards: () => IKpCard[]): KpApi {
  return API_URL ? createHttpKpApi(API_URL) : createMockKpApi(cards);
}

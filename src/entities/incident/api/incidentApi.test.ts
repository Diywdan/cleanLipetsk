import { afterEach, describe, expect, it, vi } from 'vitest';
import { createHttpIncidentApi, createMockIncidentApi } from './incidentApi';
import { incident } from '@/test/fixtures';

const inspector = { kind: 'USER', role: 'INSPECTOR', name: 'Инспектор' } as const;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('IncidentApi для пакета КНМ', () => {
  it('отправляет ISSUE_ACT в CRM и возвращает полный ответ с пакетом', async () => {
    const response = incident({
      status: 'KNM_ESCALATION',
      knmPackage: {
        status: 'generated',
        packageId: 'knm-0001',
        documents: [{ name: 'Акт', downloadUrl: 'https://crm.example/files/act.pdf' }],
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const api = createHttpIncidentApi('/api/v1');

    await expect(api.act('0001', 'ISSUE_ACT', {}, inspector)).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/incidents/0001/act', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
  });

  it('передаёт текст backend ошибки без замены', async () => {
    const message = 'Нельзя сформировать пакет: не заполнены сведения об объекте.';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message }), { status: 422, headers: { 'Content-Type': 'application/json' } }),
      ),
    );
    const api = createHttpIncidentApi('/api/v1');

    await expect(api.act('0001', 'ISSUE_ACT', {}, inspector)).rejects.toThrow(message);
  });

  it('не имитирует генерацию пакета в демо-макете и не сохраняет успех', async () => {
    const api = createMockIncidentApi('knm-api-test', () => [incident({ status: 'KNM_ESCALATION' })]);

    await expect(api.act('0001', 'ISSUE_ACT', {}, inspector)).rejects.toThrow(
      'Формирование пакета КНМ доступно только при подключении к CRM.',
    );
    await expect(api.list()).resolves.toEqual([incident({ status: 'KNM_ESCALATION' })]);
  });
});

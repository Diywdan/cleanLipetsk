import { describe, expect, it } from 'vitest';
import { incident } from '@/test/fixtures';
import { getKnmPackageDocuments } from './knmPackage';

describe('getKnmPackageDocuments', () => {
  it('принимает generated пакет без учёта регистра и оставляет только HTTP(S) ссылки', () => {
    expect(
      getKnmPackageDocuments(
        incident({
          knmPackage: {
            status: 'Generated',
            packageId: 45,
            documents: [
              { name: 'Акт', downloadUrl: 'https://crm.example/act.pdf' },
              { name: 'Предписание', downloadUrl: 'http://crm.example/order.pdf' },
              { name: 'Вредная ссылка', downloadUrl: 'javascript:alert(1)' },
              { name: 'Относительный путь', downloadUrl: '/files/report.pdf' },
            ],
          },
        }),
      ),
    ).toEqual({
      packageId: '45',
      documents: [
        { name: 'Акт', downloadUrl: 'https://crm.example/act.pdf' },
        { name: 'Предписание', downloadUrl: 'http://crm.example/order.pdf' },
      ],
    });
  });

  it.each([
    { status: 'needs_input', packageId: 'knm-1', documents: [{ downloadUrl: 'https://crm.example/act.pdf' }] },
    { status: 'generated', packageId: ' ', documents: [{ downloadUrl: 'https://crm.example/act.pdf' }] },
    { status: 'generated', packageId: 'knm-1', documents: [] },
  ])('не считает неполный пакет сформированным: %o', (knmPackage) => {
    expect(getKnmPackageDocuments(incident({ knmPackage }))).toBeNull();
  });

  it('сохраняет список сформированных документов, даже если ссылки ещё недоступны', () => {
    expect(
      getKnmPackageDocuments(
        incident({
          knmPackage: {
            status: 'generated',
            packageId: 45,
            documents: [
              { code: 'act', name: 'Акт', downloadUrl: null },
              { code: 'prescription', name: 'Предписание', downloadUrl: 'javascript:alert(1)' },
            ],
          },
        }),
      ),
    ).toEqual({
      packageId: '45',
      documents: [
        { code: 'act', name: 'Акт' },
      ],
    });
  });
});

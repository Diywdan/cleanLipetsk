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
            packageId: ' knm-0001 ',
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
      packageId: 'knm-0001',
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
    { status: 'generated', packageId: 'knm-1', documents: [{ downloadUrl: 'javascript:alert(1)' }] },
  ])('не считает неполный пакет сформированным: %o', (knmPackage) => {
    expect(getKnmPackageDocuments(incident({ knmPackage }))).toBeNull();
  });
});

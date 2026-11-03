import { describe, expect, it } from 'vitest';
import { documentPreparationMessage } from './documentPreparationMessage';
import { isDocumentServiceIssueLinkable } from './documentServiceIssueLinks';

describe('documentPreparationMessage', () => {
  it.each([
    [1, 'Для подготовки документов заполните ещё 1 поле'],
    [2, 'Для подготовки документов заполните ещё 2 поля'],
    [5, 'Для подготовки документов заполните ещё 5 полей'],
    [11, 'Для подготовки документов заполните ещё 11 полей'],
    [21, 'Для подготовки документов заполните ещё 21 поле'],
    [22, 'Для подготовки документов заполните ещё 22 поля'],
    [25, 'Для подготовки документов заполните ещё 25 полей'],
  ])('formats %i with the correct Russian noun form', (count, expected) => {
    expect(documentPreparationMessage(count)).toBe(expected);
  });
});

describe('isDocumentServiceIssueLinkable', () => {
  it.each([
    'act_composed_at',
    'inspectors',
    'action.3.place',
    'violations',
    'decision.items',
    'prescription',
  ])('links the %s readiness issue to its Document Service field', (field) => {
    expect(isDocumentServiceIssueLinkable(field)).toBe(true);
  });

  it('does not link unknown readiness fields', () => {
    expect(isDocumentServiceIssueLinkable('unknown_field')).toBe(false);
  });
});

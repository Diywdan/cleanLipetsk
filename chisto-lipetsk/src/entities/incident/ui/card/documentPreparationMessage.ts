export const documentPreparationMessage = (count: number) => {
  const lastTwoDigits = count % 100;
  const lastDigit = count % 10;
  const noun = lastTwoDigits >= 11 && lastTwoDigits <= 14
    ? 'полей'
    : lastDigit === 1
      ? 'поле'
      : lastDigit >= 2 && lastDigit <= 4
        ? 'поля'
        : 'полей';

  return `Для подготовки документов заполните ещё ${count} ${noun}`;
};

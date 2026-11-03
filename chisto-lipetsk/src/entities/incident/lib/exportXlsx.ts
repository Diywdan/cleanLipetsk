import type { IIncident } from '../types';
import { SOURCE_TITLE, STATUS_META, typoQuotes } from './presentation';
import { RESPONSIBLE_ROLE_TITLE, getPrimaryResponsible, getRecidivismCount } from './responsibles';
import { isOverdue } from './insights';

// Выгрузка реестра обращений в Excel — ровно тот список, что сейчас в ленте после фильтров.
// Библиотека тяжёлая и нужна редко, поэтому грузится при нажатии.

const date = (iso?: string) => (iso ? new Date(iso) : undefined);
const DATE_FMT = 'dd.mm.yyyy hh:mm';

export async function exportIncidentsXlsx(incidents: IIncident[], now: number, fileName: string): Promise<void> {
  const { default: writeExcelFile } = await import('write-excel-file/browser');
  const head = (value: string) => ({ value, fontWeight: 'bold' as const, wrap: true });

  await writeExcelFile(incidents, {
    columns: [
      { header: head('№'), cell: (i: IIncident) => ({ value: i.id }), width: 8 },
      { header: head('Статус'), cell: (i: IIncident) => ({ value: STATUS_META[i.status].label }), width: 16 },
      {
        header: head('Итог'),
        cell: (i: IIncident) => ({
          value: i.timeline.resolution === 'FALSE_POSITIVE' ? 'ложное срабатывание' : i.timeline.resolution === 'FIXED' ? 'устранено' : '',
        }),
        width: 18,
      },
      { header: head('Источник'), cell: (i: IIncident) => ({ value: SOURCE_TITLE[i.source] ?? i.source }), width: 20 },
      { header: head('Адрес'), cell: (i: IIncident) => ({ value: i.location.address }), width: 32 },
      { header: head('Управа'), cell: (i: IIncident) => ({ value: i.location.upravaId, type: Number }), width: 8 },
      { header: head('КП'), cell: (i: IIncident) => ({ value: i.kp?.code ?? 'не определена' }), width: 13 },
      { header: head('Реестр КП'), cell: (i: IIncident) => ({ value: i.kp?.registryNumber ?? '' }), width: 13 },
      {
        header: head('Исполнитель'),
        cell: (i: IIncident) => {
          const r = getPrimaryResponsible(i);
          return { value: r ? `${typoQuotes(r.organization.name)} (${RESPONSIBLE_ROLE_TITLE[r.role].toLowerCase()})` : '' };
        },
        width: 34,
      },
      { header: head('Нарушение (ИИ)'), cell: (i: IIncident) => ({ value: i.media.boundingBoxes.map((b) => b.label).join(', ') }), width: 28 },
      { header: head('Поступило'), cell: (i: IIncident) => ({ value: date(i.timeline.createdAt), type: Date, format: DATE_FMT }), width: 17 },
      { header: head('Подтверждено'), cell: (i: IIncident) => ({ value: date(i.timeline.validatedAt), type: Date, format: DATE_FMT }), width: 17 },
      { header: head('Срок'), cell: (i: IIncident) => ({ value: date(i.timeline.deadlineAt), type: Date, format: DATE_FMT }), width: 17 },
      { header: head('Закрыто'), cell: (i: IIncident) => ({ value: date(i.timeline.closedAt), type: Date, format: DATE_FMT }), width: 17 },
      { header: head('Срок истёк'), cell: (i: IIncident) => ({ value: isOverdue(i, now) || i.status === 'KNM_ESCALATION' ? 'да' : '' }), width: 10 },
      { header: head('Нарушений за месяц'), cell: (i: IIncident) => ({ value: getRecidivismCount(i), type: Number }), width: 12 },
    ],
    sheet: 'Обращения',
    stickyRowsCount: 1,
  }).toFile(fileName);
}

import { useId } from 'react';
import type { ExecutorProposal } from './LocationContext';

export function ExecutorExplanation({ proposal }: { proposal: ExecutorProposal }) {
  const heading = useId();
  const { executor, violationType, place, source, reason, status, confirmedBy, confirmedAt } = proposal;
  const timestamp = confirmedAt ? new Date(confirmedAt) : null;
  const when = timestamp && !Number.isNaN(timestamp.getTime())
    ? timestamp.toLocaleString('ru-RU', { timeZone: 'Europe/Moscow', dateStyle: 'short', timeStyle: 'short' })
    : null;

  return (
    <section aria-labelledby={heading} className="rounded-lg border border-border bg-[var(--inset)] p-3 text-sm">
      <h3 id={heading} className="m-0 font-semibold">Почему предложен этот исполнитель?</h3>
      <dl className="mb-2 mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5">
        <dt className="text-muted-foreground">Исполнитель</dt><dd className="m-0 font-medium">{executor?.name || 'Пока не определён'}</dd>
        {violationType && <><dt className="text-muted-foreground">Вид нарушения</dt><dd className="m-0">{violationType}</dd></>}
        {source && <><dt className="text-muted-foreground">Источник</dt><dd className="m-0">{source}</dd></>}
        {place && (
          <>
            <dt className="text-muted-foreground">{place.kind === 'house' ? 'Дом' : 'Площадка'}</dt>
            <dd className="m-0">
              {[place.code, place.address].filter(Boolean).join(' · ') || 'Адрес не указан'}
              {place.match && <div className="text-xs text-muted-foreground">{place.match}</div>}
            </dd>
          </>
        )}
      </dl>
      <p className="my-2 text-muted-foreground">{reason}</p>
      {status === 'pending' && <p className="mb-0 text-warning">Ожидает подтверждения инспектора</p>}
      {status === 'confirmed' && (
        <p className="mb-0 text-success">Подтверждено инспектором{confirmedBy && ' · ' + confirmedBy}{when && ' · ' + when + ' МСК'}</p>
      )}
    </section>
  );
}

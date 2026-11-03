import { useEffect, useState, type FC } from 'react';
import { useIncidentStore } from '../../model/incidentStore';
import type { IIncident } from '../../types';

type Props = { incident: IIncident };

export const PrimaryDocumentLinks: FC<Props> = ({ incident }) => {
  const syncDocuments = useIncidentStore((state) => state.syncDocuments);
  const [syncAttemptedFor, setSyncAttemptedFor] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(false);
  const documents = (incident.primaryPackage?.documents ?? []).filter(
    (document) => document.code === 'assignment' || document.code === 'decision',
  );
  const hasDownloadableDocuments = documents.some((document) => document.downloadUrl);
  const hasGenerationHistory = incident.timeline.history?.some(
    (event) => event.title === 'Задание и Решение сформированы',
  ) ?? false;
  const needsSync = !hasDownloadableDocuments || !hasGenerationHistory;

  useEffect(() => {
    setSyncAttemptedFor(null);
    setSyncing(false);
    setSyncError(false);
  }, [incident.id]);

  useEffect(() => {
    if (
      incident.document_service?.status === 'generated'
      && needsSync
      && syncAttemptedFor !== incident.id
    ) {
      setSyncAttemptedFor(incident.id);
      setSyncing(true);
      void syncDocuments(incident.id).then((success) => {
        setSyncError(!success);
      }).finally(() => setSyncing(false));
    }
  }, [incident.document_service?.status, incident.id, needsSync, syncAttemptedFor, syncDocuments]);

  const retrySync = () => {
    setSyncAttemptedFor(null);
    setSyncError(false);
  };
  const syncMessage = syncing
    ? hasGenerationHistory
      ? 'Загружаю ссылки на документы…'
      : 'Обновляю запись в хронике…'
    : syncError
      ? hasGenerationHistory
        ? 'Не удалось загрузить ссылки на документы.'
        : 'Не удалось обновить запись в хронике.'
      : hasGenerationHistory
        ? 'Ссылки на документы пока не получены.'
        : 'Запись о формировании документов не найдена в хронике.';

  const showSyncNotice = (
    incident.document_service?.status === 'generated'
    && needsSync
    && syncAttemptedFor === incident.id
  );
  const syncNotice = showSyncNotice ? (
    <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
      <span>{syncMessage}</span>
      {!syncing && (
        <button type="button" className="text-primary underline" onClick={retrySync}>
          Повторить
        </button>
      )}
    </div>
  ) : null;

  if (!hasDownloadableDocuments) return syncNotice;

  return (
    <>
      <ul className="m-0 flex list-inside list-disc flex-col gap-1 text-[14px]">
        {documents.map((document, index) => (
          <li key={`${document.code ?? document.name ?? ''}-${index}`}>
            {document.downloadUrl ? (
              <a
                href={document.downloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-2"
              >
                {document.name || `Документ ${index + 1}`}
              </a>
            ) : (
              document.name || `Документ ${index + 1}`
            )}
          </li>
        ))}
      </ul>
      {syncNotice}
    </>
  );
};

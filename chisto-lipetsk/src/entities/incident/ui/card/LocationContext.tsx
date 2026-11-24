import { useEffect, useState } from 'react';
import { API_URL, http } from '@/shared/api/http';
import { useIncidentStore } from '../../model/incidentStore';

type Site = { code: string; address: string | null };
type Context = {
  houseAddress: string | null;
  nearbyHouseAddress: string | null;
  accuracyMeters: number | null;
  isWasteSiteIssue: boolean;
  linkedSite: Site | null;
  nearbySites: (Site & { distanceMeters: number })[];
};

export function LocationContext({ incidentId, canLink }: { incidentId: string; canLink: boolean }) {
  const [context, setContext] = useState<Context | null>(null);
  const [error, setError] = useState('');
  const [linking, setLinking] = useState(false);

  useEffect(() => {
    if (!API_URL) return;
    let current = true;
    http<Context>(API_URL, `/incidents/${encodeURIComponent(incidentId)}/location-context`)
      .then((result) => { if (current) setContext(result); })
      .catch(() => { if (current) setError('Не удалось загрузить данные о месте'); });
    return () => { current = false; };
  }, [incidentId]);

  async function link(site: Site) {
    if (!API_URL) return;
    setLinking(true);
    setError('');
    try {
      await http(API_URL, `/cases/${encodeURIComponent(incidentId)}/kp`, { method: 'PUT', body: { kp: site.code } });
      await useIncidentStore.getState().refresh();
    } catch {
      setError('Не удалось привязать площадку');
    } finally {
      setLinking(false);
    }
  }

  if (!API_URL || (!context && !error)) return null;
  return (
    <section className="rounded-lg border border-border bg-[var(--inset)] p-3 text-sm" aria-label="Место по геопозиции">
      <h3 className="m-0 font-semibold">Место по геопозиции</h3>
      {context && (
        <>
          <p className="my-2">
            <span className="text-muted-foreground">Дом из адреса заявки</span>{' '}
            {context.houseAddress || 'не определён'}
            {context.accuracyMeters != null && (
              <span className="block text-xs text-muted-foreground">Точность геопозиции ±{Math.round(context.accuracyMeters)} м</span>
            )}
          </p>
          {!context.houseAddress && context.nearbyHouseAddress && (
            <p className="my-2"><span className="text-muted-foreground">Ориентир по реестру площадок</span>{' '}{context.nearbyHouseAddress}</p>
          )}
          {context.linkedSite && <p className="my-2">Привязана {context.linkedSite.code} · {context.linkedSite.address || 'адрес площадки не заполнен'}</p>}
          {context.nearbySites.length ? (
            <>
              <div className="mt-3 text-xs text-muted-foreground">Площадки рядом с точкой заявки</div>
              <ul className="m-0 mt-1 list-none divide-y divide-border p-0">
                {context.nearbySites.map((site) => (
                  <li key={site.code} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div>
                      <strong>{site.code}</strong> · {site.distanceMeters} м
                      <div className="text-xs text-muted-foreground">{site.address || 'Адрес площадки не указан'}</div>
                    </div>
                    {canLink && context.isWasteSiteIssue && context.linkedSite?.code !== site.code && (
                      <button type="button" disabled={linking} onClick={() => void link(site)}
                        className="rounded border border-border px-2 py-1 text-xs hover:bg-[var(--hover)] disabled:opacity-50">
                        Привязать
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          ) : <p className="mb-0 text-xs text-muted-foreground">В радиусе 50 м нет площадок из реестра.</p>}
        </>
      )}
      {error && <p role="alert" className="my-2 text-xs text-danger">{error}</p>}
    </section>
  );
}

import { useEffect, useState } from 'react';
import { API_URL, http } from '@/shared/api/http';
import { useIncidentStore } from '../../model/incidentStore';

type Site = { code: string; address: string | null };
export type ExecutorProposal = {
  executor: { id: string; name: string } | null;
  violationType: string | null;
  source: string | null;
  reason: string;
  place: { kind: 'house' | 'site'; address: string | null; code?: string; match?: string | null } | null;
  status: 'pending' | 'confirmed' | 'missing';
  confirmedBy?: string;
  confirmedAt?: string;
  token?: string;
};

type Context = {
  houseAddress: string | null;
  nearbyHouseAddress: string | null;
  accuracyMeters: number | null;
  isWasteSiteIssue: boolean;
  linkedSite: Site | null;
  nearbySites: (Site & { distanceMeters: number })[];
  executorProposal?: ExecutorProposal;
};

export function useLocationContext(incidentId: string | undefined, revision: string) {
  const [loaded, setLoaded] = useState<{ revision: string; context: Context | null; error: string } | null>(null);
  useEffect(() => {
    if (!API_URL || !incidentId) return;
    let current = true;
    http<Context>(API_URL, `/incidents/${encodeURIComponent(incidentId)}/location-context`)
      .then((context) => { if (current) setLoaded({ revision, context, error: '' }); })
      .catch(() => { if (current) setLoaded({ revision, context: null, error: 'Не удалось загрузить место и основание подбора' }); });
    return () => { current = false; };
  }, [incidentId, revision]);
  const state = loaded?.revision === revision ? loaded : null;
  return { context: state?.context ?? null, error: state?.error ?? '', loading: Boolean(API_URL && incidentId && !state) };
}

export function LocationContext({ incidentId, canLink, context, loadError }: {
  incidentId: string;
  canLink: boolean;
  context: Context | null;
  loadError: string;
}) {
  const [linkError, setLinkError] = useState('');
  const [linking, setLinking] = useState(false);
  const error = loadError || linkError;

  async function link(site: Site) {
    if (!API_URL) return;
    setLinking(true);
    setLinkError('');
    try {
      await http(API_URL, `/cases/${encodeURIComponent(incidentId)}/kp`, { method: 'PUT', body: { kp: site.code } });
      await useIncidentStore.getState().refresh();
    } catch {
      setLinkError('Не удалось привязать площадку');
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

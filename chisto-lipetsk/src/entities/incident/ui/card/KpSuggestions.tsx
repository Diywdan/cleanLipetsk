import React, { useEffect, useState } from 'react';
import { API_URL, http } from '@/shared/api/http';
import { useIncidentStore } from '../../model/incidentStore';

type Candidate = {
  kp_id: string; code: string; address_raw?: string;
  match: string; suggested_executor: { id: string; name: string } | null;
  reason: string; requires_confirmation: boolean;
};

export const KpSuggestions: React.FC<{ id: string }> = ({ id }) => {
  const [street, setStreet] = useState('');
  const [house, setHouse] = useState('');
  const [rows, setRows] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);
  const [selected, setSelected] = useState('');
  useEffect(() => {
    if (!API_URL) return;
    let active = true;
    setBusy(true);
    http<Candidate[]>(API_URL, `/cases/${encodeURIComponent(id)}/kp-candidates`)
      .then((items) => { if (active) { setRows(items); setSearched(true); } })
      .catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : 'Не удалось найти площадки'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [id]);
  if (!API_URL) return null;
  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(''); setSelected('');
    try {
      const query = new URLSearchParams({ street: street.trim(), house: house.trim() });
      setRows(await http<Candidate[]>(API_URL!, `/cases/${encodeURIComponent(id)}/kp-candidates?${query}`));
      setSearched(true);
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось найти площадки'); }
    finally { setBusy(false); }
  }
  async function choose(row: Candidate) {
    setBusy(true); setError('');
    try {
      await http(API_URL!, `/cases/${encodeURIComponent(id)}/kp`, { method: 'PUT', body: { kp: row.code } });
      await useIncidentStore.getState().refresh();
      setSelected(row.code);
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось выбрать площадку'); }
    finally { setBusy(false); }
  }
  return (
    <section className="rounded-lg border border-border bg-[var(--inset)] p-3" aria-label="Подбор площадки и ответственного">
      <h3 className="m-0 text-sm font-semibold">Подбор КП и ответственного</h3>
      <p className="mt-1 text-xs text-muted-foreground">Укажите улицу и дом. Поиск рядом с точкой обращения, до 2 км. Выбор КП не направляет дело исполнителю — подтвердите его внизу карточки.</p>
      <form onSubmit={search} className="flex flex-wrap gap-2">
        <label className="flex min-w-0 flex-1 flex-col text-xs">Улица
          <input required value={street} onChange={(e) => setStreet(e.target.value)} placeholder="Например, Ангарская" className="mt-1 rounded border border-border bg-background p-2 text-sm" />
        </label>
        <label className="flex w-24 flex-col text-xs">Дом
          <input required value={house} onChange={(e) => setHouse(e.target.value)} placeholder="27" className="mt-1 rounded border border-border bg-background p-2 text-sm" />
        </label>
        <button type="submit" disabled={busy} className="mt-4 rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">Найти КП</button>
      </form>
      {busy && <p role="status" className="text-xs">Загрузка…</p>}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      {!busy && searched && rows.length === 0 && <p className="text-xs text-muted-foreground">Совпадений нет. Проверьте адрес или уточните площадку в реестре; исполнитель автоматически не назначен.</p>}
      {rows.length > 1 && <p className="text-xs text-warning">Найдено несколько площадок — выберите нужную.</p>}
      {rows.map((row) => <div key={row.kp_id} className="mt-3 border-t border-border pt-2 text-sm">
        <strong>{row.code}</strong> · {row.address_raw || 'Адрес не заполнен'}
        <div className="mt-1 text-xs text-muted-foreground">{row.match === 'address' ? 'Совпадение улицы и дома' : 'Рядом с точкой обращения'}</div>
        <p className="my-1">{row.suggested_executor ? `Предложение: ${row.suggested_executor.name}` : 'Исполнитель не определён'}</p>
        <p className="my-1 text-xs text-muted-foreground">{row.reason}</p>
        <button type="button" disabled={busy} onClick={() => choose(row)} className="mt-1 rounded border border-border px-3 py-2 text-xs disabled:opacity-50">Выбрать эту КП</button>
      </div>)}
      {selected && <p role="status" className="text-xs text-success">Выбрана {selected}. Проверьте тип проблемы и исполнителя перед подтверждением дела.</p>}
    </section>
  );
};
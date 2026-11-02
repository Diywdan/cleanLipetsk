import { useEffect, useState, type FC, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { documentPreparationMessage } from './documentPreparationMessage';
import { useIncidentStore } from '../../model/incidentStore';
import type { IDocumentServiceData, IDocumentServiceOptions, IIncident } from '../../types';

type Props = { incident: IIncident };

const blankValues: IDocumentServiceData = {
  subject: null,
  control_kind_id: null,
  control_form_id: null,
  control_body_id: null,
  control_object_id: null,
  controlled_organization_id: null,
  assignment_approved_by_signatory_id: null,
  planned_start_at: null,
  planned_end_at: null,
  basis_kind: null,
  basis_document_number: null,
  basis_document_date: null,
  basis_description: null,
  decision_item_kind: 'issue_prescription',
  decision_item_description: 'выдать предписание об устранении нарушений',
};

const REQUIRED_ISSUES = [
  'control_kind', 'control_form', 'control_body', 'controlled_organization', 'control_object',
  'approver', 'planned_start_at', 'planned_end_at', 'bases', 'decision.items',
] as const;

const LINKABLE_ISSUES = new Set<string>([
  ...REQUIRED_ISSUES,
  'control_object.address',
  'inspectors', 'requisites', 'requisites.inn', 'requisites.legal_address',
  'assignment_date', 'actual_start_at', 'actual_end_at', 'actions',
  'decision', 'decision.decision_date',
]);

const isLinkableIssue = (field: string) => LINKABLE_ISSUES.has(field)
  || /^action\.\d+\.(started_at|ended_at|place)$/.test(field);

export const DocumentServicePanel: FC<Props> = ({ incident }) => {
  const api = useIncidentStore((s) => s.api);
  const save = useIncidentStore((s) => s.saveDocumentServiceData);
  const storeError = useIncidentStore((s) => s.error);
  const [expanded, setExpanded] = useState(false);
  const [showAllFields, setShowAllFields] = useState(false);
  const [options, setOptions] = useState<IDocumentServiceOptions | null>(null);
  const [values, setValues] = useState<IDocumentServiceData>(blankValues);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const readiness = incident.document_service?.readiness;
  const issues = readiness?.issues ?? [];
  const missing = new Set(issues.map((issue) => issue.field));
  const missingRequired = REQUIRED_ISSUES.filter((field) => missing.has(field)).length;
  const filledRequired = REQUIRED_ISSUES.length - missingRequired;
  const templatesMissing = readiness?.missing_templates ?? [];
  const readinessBlockers = issues.length + templatesMissing.length;
  const isGenerated = incident.document_service?.status === 'generated';

  useEffect(() => {
    let active = true;
    if (!expanded || !api || options) return;

    setLoading(true);
    api.documentServiceOptions(incident.id)
      .then((result) => {
        if (!active) return;
        setOptions(result);
        setValues({ ...blankValues, ...result.values });
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (active) setLoadError(error instanceof Error ? error.message : 'Не удалось загрузить данные мероприятия');
      })
      .finally(() => { if (active) setLoading(false); });

    return () => { active = false; };
  }, [api, expanded, incident.id, options]);

  useEffect(() => {
    if (isGenerated) setExpanded(false);
  }, [isGenerated]);

  const set = <K extends keyof IDocumentServiceData>(key: K, value: IDocumentServiceData[K]) =>
    setValues((current) => ({ ...current, [key]: value }));
  const selectId = (value: string) => value ? Number(value) : null;
  const signatories = options?.signatories.filter(
    (row) => values.control_body_id === null || row.control_body_id === values.control_body_id,
  ) ?? [];
  const showField = (...issueFields: string[]) => showAllFields || issueFields.some((field) => missing.has(field));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    await save(incident.id, values);
    setSaving(false);
  };

  const label = 'flex flex-col gap-1 text-[12px] text-muted-foreground';
  const control = 'h-9 rounded-md border border-input bg-background px-2 text-[13px] text-foreground';
  const section = 'grid grid-cols-1 gap-2 sm:grid-cols-2';

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
        <span className="text-muted-foreground">
          {isGenerated
            ? 'Задание и Решение сформированы'
            : `Основные поля CRM: ${filledRequired} из ${REQUIRED_ISSUES.length}`}
        </span>
        {!isGenerated && readiness && (
          <span className={readinessBlockers > 0 ? 'text-danger' : 'text-muted-foreground'}>
            {readinessBlockers > 0
              ? documentPreparationMessage(readinessBlockers)
              : 'Проверка document-service: замечаний нет'}
          </span>
        )}
        {!isGenerated && (
          <Button type="button" variant="link" size="sm" className="h-auto p-0" onClick={() => setExpanded((open) => !open)}>
            {expanded ? 'Свернуть' : 'Заполнить данные мероприятия'}
          </Button>
        )}
        {incident.document_service?.url && (
          <a
            href={`/api/v1/incidents/${encodeURIComponent(incident.id)}/document-service/launch`}
            target="_blank"
            rel="noreferrer"
            className="text-primary underline"
          >
            Открыть сервис документов
          </a>
        )}
      </div>

      {!isGenerated && templatesMissing.length > 0 && (
        <p className="m-0 text-[12px] text-muted-foreground">
          Не настроены шаблоны: {templatesMissing.join(', ')}
        </p>
      )}

      {!isGenerated && issues.length > 0 && (
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-[12px] text-muted-foreground">
          {issues.map((issue) => (
            <li key={`${issue.field}-${issue.document ?? ''}`}>
              {isLinkableIssue(issue.field) && incident.document_service?.url ? (
                <a
                  href={`/api/v1/incidents/${encodeURIComponent(incident.id)}/document-service/launch?field=${encodeURIComponent(issue.field)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline"
                  title="Открыть нужное поле в полной карточке document-service"
                >{issue.message}</a>
              ) : issue.message}
            </li>
          ))}
        </ul>
      )}

      {expanded && (
        <div className="document-service-fields rounded-md border border-input p-3">
          <div className="flex flex-col gap-3">
          {loading && <span className="text-[12px] text-muted-foreground">Загружаю варианты…</span>}
          {loadError && <span role="alert" className="text-[12px] text-danger">{loadError}</span>}

          {options && (
            <>
              {missingRequired === 0 && !showAllFields && (
                <span className="text-[12px] text-muted-foreground">Обязательные поля заполнены.</span>
              )}
              <form onSubmit={submit} className="flex flex-col gap-3">
                {(showField('subject', 'control_kind', 'control_form', 'control_body', 'controlled_organization', 'control_object', 'approver')
                  || showAllFields) && (
                  <section className="flex flex-col gap-2">
                    <b className="text-[12px] font-medium">Параметры мероприятия</b>
                    <div className={section}>
                      {showField('subject') && (
                        <label className={`${label} sm:col-span-2`}>Предмет контрольного мероприятия
                          <select className={control} value={values.subject ?? ''} onChange={(e) => set('subject', e.target.value || null)}>
                            <option value="">Выберите…</option>{options.subjects.map((x) => <option key={x.value} value={x.value}>{x.value}</option>)}
                          </select>
                        </label>
                      )}
                      {showField('control_kind') && (
                        <label className={label}>Вид контроля
                          <select className={control} value={values.control_kind_id ?? ''} onChange={(e) => set('control_kind_id', selectId(e.target.value))}>
                            <option value="">Выберите…</option>{options.control_kinds.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                          </select>
                        </label>
                      )}
                      {showField('control_form') && (
                        <label className={label}>Форма мероприятия
                          <select className={control} value={values.control_form_id ?? ''} onChange={(e) => set('control_form_id', selectId(e.target.value))}>
                            <option value="">Выберите…</option>{options.control_forms.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                          </select>
                        </label>
                      )}
                      {showField('control_body') && (
                        <label className={label}>Орган контроля
                          <select className={control} value={values.control_body_id ?? ''} onChange={(e) => {
                            const next = selectId(e.target.value);
                            setValues((current) => ({ ...current, control_body_id: next, assignment_approved_by_signatory_id: null }));
                          }}>
                            <option value="">Выберите…</option>{options.control_bodies.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                          </select>
                        </label>
                      )}
                      {showField('controlled_organization') && (
                        <label className={label}>Контролируемое лицо
                          <select className={control} value={values.controlled_organization_id ?? ''} onChange={(e) => set('controlled_organization_id', selectId(e.target.value))}>
                            <option value="">Выберите…</option>{options.organizations.map((x) => <option key={x.id} value={x.id}>{x.name}{x.inn ? ` · ИНН ${x.inn}` : ''}</option>)}
                          </select>
                        </label>
                      )}
                      {showField('control_object') && (
                        <label className={label}>Объект контроля
                          <select className={control} value={values.control_object_id ?? ''} onChange={(e) => set('control_object_id', selectId(e.target.value))}>
                            <option value="">Выберите…</option>{options.control_objects.map((x) => <option key={x.id} value={x.id}>{x.name}{x.address ? ` · ${x.address}` : ''}</option>)}
                          </select>
                        </label>
                      )}
                      {showField('approver') && (
                        <label className={label}>Подписант задания и решения
                          <select className={control} value={values.assignment_approved_by_signatory_id ?? ''} onChange={(e) => set('assignment_approved_by_signatory_id', selectId(e.target.value))}>
                            <option value="">Выберите…</option>{signatories.map((x) => <option key={x.id} value={x.id}>{x.name} — {x.position}</option>)}
                          </select>
                        </label>
                      )}
                    </div>
                  </section>
                )}

                {(showField('planned_start_at', 'planned_end_at', 'bases') || showAllFields) && (
                  <section className="flex flex-col gap-2">
                    <b className="text-[12px] font-medium">Сроки и основание</b>
                    <div className={section}>
                      {showField('planned_start_at') && (
                        <label className={label}>Планируемое начало мероприятия
                          <input type="datetime-local" className={control} value={values.planned_start_at?.slice(0, 16) ?? ''} onChange={(e) => set('planned_start_at', e.target.value || null)} />
                        </label>
                      )}
                      {showField('planned_end_at') && (
                        <label className={label}>Планируемое окончание мероприятия
                          <input type="datetime-local" className={control} value={values.planned_end_at?.slice(0, 16) ?? ''} onChange={(e) => set('planned_end_at', e.target.value || null)} />
                        </label>
                      )}
                      {showField('bases') && (
                        <>
                          <label className={label}>Тип основания
                            <select className={control} value={values.basis_kind ?? ''} onChange={(e) => set('basis_kind', e.target.value || null)}>
                              <option value="">Выберите…</option>{options.basis_kinds.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
                            </select>
                          </label>
                          <label className={label}>Номер основания
                            <input className={control} value={values.basis_document_number ?? ''} onChange={(e) => set('basis_document_number', e.target.value || null)} />
                          </label>
                          <label className={label}>Дата основания
                            <input type="date" className={control} value={values.basis_document_date?.slice(0, 10) ?? ''} onChange={(e) => set('basis_document_date', e.target.value || null)} />
                          </label>
                          <label className={label}>Описание основания
                            <input className={control} value={values.basis_description ?? ''} onChange={(e) => set('basis_description', e.target.value || null)} />
                          </label>
                        </>
                      )}
                    </div>
                  </section>
                )}

                {(showField('decision.items') || showAllFields) && (
                  <section className="flex flex-col gap-2">
                    <b className="text-[12px] font-medium">Решение</b>
                    <div className={section}>
                      <label className={label}>Пункт решения
                        <select className={control} value={values.decision_item_kind ?? ''} onChange={(e) => set('decision_item_kind', e.target.value || null)}>
                          {options.decision_item_kinds.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
                        </select>
                      </label>
                      <label className={`${label} sm:col-span-2`}>Текст пункта решения
                        <textarea className={`${control} min-h-16 py-2`} value={values.decision_item_description ?? ''} onChange={(e) => set('decision_item_description', e.target.value || null)} />
                      </label>
                    </div>
                  </section>
                )}

                <div className="flex flex-wrap items-center gap-2">
                  <Button type="submit" variant="outline" disabled={saving || loading}>
                    {saving ? 'Сохраняю и проверяю…' : 'Сохранить данные и проверить документы'}
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setShowAllFields((show) => !show)}>
                    {showAllFields ? 'Скрыть заполненные поля' : 'Показать все данные'}
                  </Button>
                </div>
                {storeError && <span role="alert" className="text-[12px] text-danger">{storeError}</span>}
              </form>
            </>
          )}
          </div>
        </div>
      )}
    </div>
  );
};

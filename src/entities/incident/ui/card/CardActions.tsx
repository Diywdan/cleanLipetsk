import React, { useState } from 'react';
import { CheckCircle2, FileDown, Gavel } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { IIncident } from '../../types';
import type { UserRole } from '@/entities/user/types';
import { useIncidentStore } from '../../model/incidentStore';
import { formatDeadline } from '../../lib/presentation';
import { isDeadlineFixed, resolveDeadlineHours, type DeadlineHours } from '../../lib/sla';
import { can, type Actor, type IncidentAction } from '../../lib/workflow';
import { getPrimaryResponsible } from '../../lib/responsibles';
import { useNow } from '@/shared/lib/time';
import { useAuthStore } from '@/entities/user/model/authStore';
import { PhotoReportForm } from './PhotoReportForm';
import { ExecutorPicker } from './ExecutorPicker';
import { useExecutorStore } from '@/entities/executor/model/executorStore';
import { isMismatch, reassignState, typeAfterExecutorChange, type ReassignChoice } from '@/entities/executor/lib/reassign';
import afterPhoto from '@/assets/demo/kp-after.svg';

// Нижняя панель карточки: что может сделать текущая роль с делом в текущем статусе.
// Доступность кнопок — из правил lib/workflow.ts, тех же, что проверяет API.

const DISMISS_REASONS = ['Нарушения на снимке нет', 'Повторное обращение', 'Не территория площадки'] as const;

export const CardActions: React.FC<{ incident: IIncident; role: UserRole }> = ({ incident, role }) => {
  const { id, status, source } = incident;
  const now = useNow(30_000);
  const s = useIncidentStore();
  const [deadline, setDeadline] = useState<DeadlineHours>(48);
  const [step, setStep] = useState<'dismiss' | 'return' | null>(null);
  const [comment, setComment] = useState('');
  const [docError, setDocError] = useState<string | null>(null);
  const userName = useAuthStore((u) => u.currentUser?.name);

  // Исполнитель и тип по справочнику CRM (без бэкенда справочника нет — выбор не показывается)
  const executors = useExecutorStore((x) => x.executors);
  // Основной исполнитель: содержатель площадки, а в делах о вывозе — регоператор
  const maintainer = getPrimaryResponsible(incident)?.organization;
  const current: ReassignChoice = { executorId: maintainer?.id ?? '', typeId: incident.violationType?.id ?? '' };
  const [picked, setPicked] = useState<ReassignChoice | null>(null);
  const choice = picked ?? current;
  const reassign = reassignState(executors, current, choice);

  const actor: Actor = { kind: 'USER', role, name: '' };
  const allowed = (a: IncidentAction) => can(a, incident, actor, now);

  // Длинные подписи («Сформировать акт и предписание (PDF)») переносятся, а не обрезаются
  const btn = 'h-auto min-h-10 whitespace-normal py-2 text-[14px]';
  const primary = `${btn} font-semibold hover:bg-primary/90 shadow-[0_0_28px_-6px_var(--primary)]`;
  const secondary = `${btn} bg-transparent hover:bg-[var(--hover)]`;
  const hint = (text: string) => <p className="m-0 text-[14px] text-muted-foreground">{text}</p>;
  const note = (tone: 'ok' | 'bad', text: string) => (
    <p
      className={`m-0 flex items-start gap-2 rounded-md px-3 py-2.5 text-[14px] ${tone === 'ok' ? 'text-success' : 'text-danger'}`}
      style={{ background: tone === 'ok' ? 'var(--st-done-bg)' : 'var(--st-knm-bg)' }}
    >
      {tone === 'ok' && <CheckCircle2 className="mt-0.5 size-4 shrink-0" />}
      {text}
    </p>
  );

  const error = s.error && (
    <p role="alert" className="m-0 rounded-md px-3 py-2 text-[13px] text-danger" style={{ background: 'var(--st-knm-bg)' }}>
      {s.error}
    </p>
  );

  const body = (() => {
    // ── Новое: подтвердить или отклонить ──
    if (allowed('CONFIRM')) {
      if (step === 'dismiss') {
        return (
          <div className="flex flex-col gap-2">
            <span className="eyebrow">Почему сигнал ложный</span>
            {DISMISS_REASONS.map((r) => (
              <Button key={r} variant="outline" className={`${secondary} justify-start`} onClick={() => s.dismissIncident(id, r)}>
                {r}
              </Button>
            ))}
            <button type="button" onClick={() => setStep(null)} className="mt-1 cursor-pointer text-[13px] text-muted-foreground hover:text-foreground">
              Отмена
            </button>
          </div>
        );
      }
      return (
        <div className="flex flex-col gap-3">
          {isDeadlineFixed(source) ? (
            <p className="m-0 text-[14px] text-foreground">
              Срок устранения установлен регламентом: <b className="font-semibold">{formatDeadline(resolveDeadlineHours(source, 48))}</b>
            </p>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="eyebrow">Срок устранения</span>
              <div className="flex rounded-md border border-input p-0.5" role="radiogroup" aria-label="Срок устранения">
                {([24, 48, 72] as const).map((hours) => (
                  <button
                    key={hours}
                    type="button"
                    role="radio"
                    aria-checked={deadline === hours}
                    onClick={() => setDeadline(hours)}
                    className={`font-num cursor-pointer rounded px-3 py-1 text-[13.5px] transition-colors ${
                      deadline === hours ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-muted'
                    }`}
                  >
                    {hours} ч
                  </button>
                ))}
              </div>
            </div>
          )}
          {executors.length > 0 && (
            <ExecutorPicker
              executors={executors}
              current={current}
              currentNames={{ executor: maintainer?.name ?? 'не определён', type: incident.violationType?.name ?? null }}
              choice={choice}
              state={reassign}
              mismatch={isMismatch(executors, current)}
              onChange={setPicked}
              onExecutorChange={(executorId) =>
                setPicked({
                  executorId,
                  // вернулись к пришедшему ведомству — вместе с ним возвращается и пришедший тип
                  typeId: typeAfterExecutorChange(executors, executorId, choice.typeId) || (executorId === current.executorId ? current.typeId : ''),
                })
              }
            />
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[auto_1fr]">
            <Button variant="outline" onClick={() => setStep('dismiss')} className={`${secondary} text-danger`}>
              Ложное срабатывание
            </Button>
            <Button onClick={() => s.confirmIncident(id, deadline, reassign.payload)} disabled={!reassign.valid} className={primary}>
              Подтвердить и направить исполнителю
            </Button>
          </div>
        </div>
      );
    }

    // ── В работе: отчёт исполнителя ──
    if (allowed('SUBMIT_REPORT')) {
      return (
        <PhotoReportForm
          incident={incident}
          demoPhoto={afterPhoto}
          onSubmit={(report) => s.submitPhotoReport(id, report)}
          buttonClass={primary}
          secondaryClass={secondary}
        />
      );
    }

    // ── На проверке: принять или вернуть ──
    if (allowed('APPROVE')) {
      if (step === 'return') {
        return (
          <div className="flex flex-col gap-2">
            <label className="eyebrow" htmlFor={`ret-${id}`}>Что доделать</label>
            <textarea
              id={`ret-${id}`}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={2}
              placeholder="Например: остался навал КГМ справа от площадки"
              className="w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-[14px] outline-none focus:border-primary"
            />
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" className={secondary} onClick={() => setStep(null)}>Отмена</Button>
              <Button
                className={primary}
                onClick={() => {
                  s.returnIncident(id, comment.trim() || undefined);
                  setStep(null);
                  setComment('');
                }}
              >
                Вернуть
              </Button>
            </div>
          </div>
        );
      }
      return (
        <div className="flex flex-col gap-3">
          {hint('Сравните снимки «было» и «стало»: передвиньте шторку на фото.')}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Button variant="outline" onClick={() => setStep('return')} className={secondary}>
              Вернуть на доработку
            </Button>
            <Button onClick={() => s.approveIncident(id)} className={primary}>
              Принять и закрыть
            </Button>
          </div>
        </div>
      );
    }

    // ── Срок вышел, а дело ещё в работе: инспектор передаёт на КНМ вручную ──
    if (allowed('ESCALATE')) {
      return (
        <div className="flex flex-col gap-3">
          {note('bad', 'Срок устранения истёк, фотоотчёта нет.')}
          <Button onClick={() => s.triggerKnmEscalation(id, false)} className={primary}>
            <Gavel /> Передать на КНМ
          </Button>
        </div>
      );
    }

    if (status === 'CLOSED') {
      return incident.timeline.resolution === 'FALSE_POSITIVE'
        ? note('ok', 'Сигнал не подтвердился. Дело закрыто без передачи исполнителю.')
        : note('ok', 'Нарушение устранено. Дело закрыто.');
    }

    if (status === 'KNM_ESCALATION') {
      return (
        <div className="flex flex-col gap-3">
          {note('bad', 'Срок устранения истёк. Материалы готовятся к передаче на контрольно-надзорное мероприятие.')}
          {allowed('ISSUE_ACT') && (
            <Button
              onClick={async () => {
                setDocError(null);
                try {
                  const { generateKnmAct } = await import('../../lib/generateKnmAct');
                  await generateKnmAct(incident, userName);
                  await s.issueKnmAct(id);
                } catch (e) {
                  setDocError(e instanceof Error ? e.message : 'Не удалось сформировать документы');
                }
              }}
              className={primary}
            >
              <FileDown /> Сформировать акт и предписание (PDF)
            </Button>
          )}
          {docError && <p role="alert" className="m-0 text-[13px] text-danger">{docError}</p>}
        </div>
      );
    }

    // Ждём действия другой стороны
    if (role === 'ADMIN') return hint('Режим просмотра: решения по делу принимают инспектор и исполнитель.');
    if (status === 'NEW') return hint('Обращение на проверке у инспектора ДРТ.');
    if (status === 'IN_PROGRESS') return hint(role === 'INSPECTOR' ? 'Ждём фотоотчёт исполнителя.' : 'Срок вышел — решение за инспектором.');
    if (status === 'VERIFICATION') return hint('Фотоотчёт отправлен, инспектор проверяет.');
    return null;
  })();

  return (
    <div className="flex flex-col gap-3">
      {error}
      {body}
    </div>
  );
};

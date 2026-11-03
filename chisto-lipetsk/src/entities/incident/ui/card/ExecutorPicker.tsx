import React, { useState } from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { IExecutorRef } from '@/entities/executor/types';
import type { ReassignChoice, ReassignState } from '@/entities/executor/lib/reassign';

// Исполнитель и тип нарушения при подтверждении дела. Свёрнут в строку, пока всё сходится;
// дело с расхождением со справочником открывает выбор сразу. Правило пары — lib/reassign.ts.

interface Props {
  executors: IExecutorRef[];
  current: ReassignChoice;
  currentNames: { executor: string; type: string | null };
  choice: ReassignChoice;
  state: ReassignState;
  mismatch: boolean;
  onChange: (choice: ReassignChoice) => void;
  onExecutorChange: (executorId: string) => void;
}

const trigger = 'w-full min-w-0 flex-1 text-[14px] data-[size=default]:h-9';

export const ExecutorPicker: React.FC<Props> = ({ executors, current, currentNames, choice, state, mismatch, onChange, onExecutorChange }) => {
  const [editing, setEditing] = useState(false);
  const open = editing || mismatch || state.changed;

  if (!open) {
    return (
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="eyebrow">Исполнитель</span>
          <p className="m-0 mt-0.5 text-[14px] text-foreground">
            {currentNames.executor}
            {currentNames.type && <span className="text-muted-foreground"> · {currentNames.type}</span>}
          </p>
        </div>
        <button type="button" onClick={() => setEditing(true)} className="shrink-0 cursor-pointer text-[13px] text-primary hover:underline">
          Изменить
        </button>
      </div>
    );
  }

  // Пришедшее значение, которого нет среди вариантов (ведомство выключено, тип чужой), показываем как есть
  const executorItems = executors.some((x) => x.id === current.executorId)
    ? executors
    : [{ id: current.executorId, name: `${currentNames.executor} — нет в справочнике`, kind: 'OMSU' as const, types: [] }, ...executors];
  const typeItems =
    choice.executorId === current.executorId && current.typeId && !state.types.some((t) => t.id === current.typeId)
      ? [{ id: current.typeId, name: `${currentNames.type ?? current.typeId} — не у этого исполнителя` }, ...state.types]
      : state.types;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-2">
        <label className="flex min-w-0 items-center gap-3">
          <span className="eyebrow w-28 shrink-0">Исполнитель</span>
          <Select value={choice.executorId} onValueChange={onExecutorChange}>
            <SelectTrigger className={trigger} aria-label="Исполнитель">
              <SelectValue placeholder="Выберите ведомство" />
            </SelectTrigger>
            <SelectContent position="popper" className="w-(--radix-select-trigger-width) min-w-64">
              {executorItems.filter((x) => x.id).map((x) => (
                <SelectItem key={x.id} value={x.id} className="text-[14px]">{x.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <label className="flex min-w-0 items-center gap-3">
          <span className="eyebrow w-28 shrink-0">Тип нарушения</span>
          <Select value={choice.typeId} onValueChange={(typeId) => onChange({ ...choice, typeId })} disabled={typeItems.length === 0}>
            <SelectTrigger className={trigger} aria-label="Тип нарушения">
              <SelectValue placeholder="Выберите тип" />
            </SelectTrigger>
            <SelectContent position="popper" className="w-(--radix-select-trigger-width) min-w-64">
              {typeItems.map((t) => (
                <SelectItem key={t.id} value={t.id} className="text-[14px]">{t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
      </div>
      {state.problem ? (
        <p className="m-0 text-[13px] text-warning">{state.problem}</p>
      ) : state.changed ? (
        <p className="m-0 text-[13px] text-muted-foreground">Замена попадёт в хронику дела.</p>
      ) : (
        mismatch && <p className="m-0 text-[13px] text-muted-foreground">Поправьте пару или подтвердите как есть — CRM отметит это в хронике.</p>
      )}
      {(state.changed || (editing && !mismatch)) && (
        <button
          type="button"
          onClick={() => {
            onChange(current);
            setEditing(false);
          }}
          className="cursor-pointer self-start text-[13px] text-muted-foreground hover:text-foreground"
        >
          Вернуть как было
        </button>
      )}
    </div>
  );
};

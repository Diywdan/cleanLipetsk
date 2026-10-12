import React from "react";
import { useIncidentCard } from "../lib/useIncidentCard";
import { getStatusBadge } from "../lib/cardUtils";
import { Button } from "@/components/ui/button";
import { ImageCompareSlider } from "@/shared/components/image-slider/ImageCompareSlider";
import { IncidentAuditLog } from "./IncidentAuditLog";
import afterPhoto from '@/assets/25.jpg';

import { Camera, CheckCircle2, AlertTriangle, MapPin, MousePointerClick, FileDown } from "lucide-react";
import { generateKnmAct } from "../lib/generateKnmAct";
import {
  getPrimaryResponsible,
  ORGANIZATION_KIND_TITLE,
  RESPONSIBLE_ROLE_TITLE,
} from "../lib/responsibles";
import { SOURCE_TITLE, formatDateTime, formatDeadline, typoQuotes } from "../lib/presentation";
import { isDeadlineFixed, resolveDeadlineHours } from "../lib/sla";
import type { UserRole } from "@/entities/user/types";
import { useStandStore } from "@/shared/theme/standStore";
import { DispatchCard } from "./card/DispatchCard";
import { DossierCard } from "./card/DossierCard";
import { ProCard } from "./card/ProCard";

interface TProps {
  userRole: UserRole;
}

// Заголовок раздела карточки
const SectionTitle: React.FC<{ children: React.ReactNode; aside?: React.ReactNode }> = ({ children, aside }) => (
  <div className="mb-3 flex items-center justify-between gap-3">
    <h3 className="text-[15px] font-semibold text-foreground">{children}</h3>
    {aside}
  </div>
);

// Пара «подпись — значение»
const Field: React.FC<{ label: string; children: React.ReactNode; wide?: boolean }> = ({ label, children, wide }) => (
  <div className={wide ? "col-span-2" : undefined}>
    <dt className="text-[13px] text-muted-foreground">{label}</dt>
    <dd className="mt-0.5 text-[14px] text-foreground">{children}</dd>
  </div>
);

const GosCard: React.FC<TProps> = ({ userRole }) => {
  // 1. Достаем из Zustand-стора текущий выбранный инцидент и экшены маршрутной карты
  const {
    selectedIncident,
    confirmIncident,
    submitPhotoReport,
    approveIncident,
    rejectIncident,
    selectedDeadline,
    setSelectedDeadline,
    showAiLayer,
    setShowAiLayer,
    formattedTime,
    isExpired,
    slalabel
  } = useIncidentCard();

  // Ничего не выбрано — подсказка вместо карточки
  if (!selectedIncident) {
    return (
      <div className="flex h-full min-h-60 flex-col items-center justify-center gap-3 rounded-lg border border-border bg-card p-8 text-center">
        <MousePointerClick className="size-8 text-muted-foreground" strokeWidth={1.5} />
        <div className="text-[16px] font-medium text-foreground">Обращение не выбрано</div>
        <p className="max-w-xs text-[14px] text-muted-foreground">
          Выберите точку на карте или строку в реестре, чтобы открыть карточку обращения.
        </p>
      </div>
    );
  }

  const { id, status, source, location, kp, responsibles, timeline, media } =
    selectedIncident;
  const primary = getPrimaryResponsible(selectedIncident);
  const fixedDeadline = isDeadlineFixed(source);

  // Блок действий внизу карточки зависит от роли и статуса
  const actions = (() => {
    if (userRole === "INSPECTOR" && status === "NEW") {
      return (
        <div className="flex flex-col gap-3">
          {fixedDeadline ? (
            <p className="flex items-start gap-2 text-[14px] text-foreground">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-primary" />
              <span>
                Срок устранения установлен регламентом:{" "}
                <b className="font-semibold">{formatDeadline(resolveDeadlineHours(source, 48))}</b>
              </span>
            </p>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-[14px] text-foreground">Срок устранения</span>
              <div className="flex rounded-md border border-input p-0.5" role="radiogroup" aria-label="Срок устранения">
                {([24, 48, 72] as const).map((hours) => (
                  <button
                    key={hours}
                    type="button"
                    role="radio"
                    aria-checked={selectedDeadline === hours}
                    onClick={() => setSelectedDeadline(hours)}
                    className={`cursor-pointer rounded px-3 py-1 text-[14px] transition-colors ${
                      selectedDeadline === hours
                        ? "bg-primary text-primary-foreground"
                        : "text-foreground hover:bg-muted"
                    }`}
                  >
                    {hours} ч
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Button variant="outline" onClick={() => rejectIncident(id)} className="h-10 text-[14px] text-danger">
              Отклонить: ложное срабатывание
            </Button>
            <Button onClick={() => confirmIncident()} className="h-10 text-[14px] hover:bg-primary/90">
              Подтвердить и направить в УК
            </Button>
          </div>
        </div>
      );
    }

    if (userRole === "UK" && status === "IN_PROGRESS") {
      return (
        <div className="flex flex-col gap-3">
          <p className="text-[14px] text-muted-foreground">
            Устраните нарушение в границах площадки и приложите фото результата.
          </p>
          <Button onClick={() => submitPhotoReport(id, afterPhoto)} className="h-10 text-[14px] hover:bg-primary/90">
            <Camera /> Отправить фотоотчёт
          </Button>
        </div>
      );
    }

    if (userRole === "INSPECTOR" && status === "VERIFICATION") {
      return (
        <div className="flex flex-col gap-3">
          <p className="text-[14px] text-muted-foreground">
            Сравните снимки «было» и «стало»: передвиньте шторку на фото.
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Button variant="outline" onClick={() => rejectIncident(id)} className="h-10 text-[14px]">
              Вернуть на доработку
            </Button>
            <Button onClick={() => approveIncident(id)} className="h-10 text-[14px] hover:bg-primary/90">
              Принять и закрыть
            </Button>
          </div>
        </div>
      );
    }

    if (status === "CLOSED") {
      return (
        <p className="flex items-center gap-2 rounded-md bg-[#E5F4EB] px-3 py-2.5 text-[14px] text-success">
          <CheckCircle2 className="size-4 shrink-0" /> Нарушение устранено. Дело закрыто.
        </p>
      );
    }

    if (status === "KNM_ESCALATION") {
      return (
        <div className="flex flex-col gap-3">
          <p className="rounded-md bg-[#FCEBED] px-3 py-2.5 text-[14px] text-danger">
            Срок устранения истёк. Материалы готовятся к передаче на контрольно-надзорное мероприятие.
          </p>
          {userRole === "INSPECTOR" && (
            <Button onClick={() => generateKnmAct(selectedIncident)} className="h-10 text-[14px] hover:bg-primary/90">
              <FileDown /> Сформировать акт и предписание (PDF)
            </Button>
          )}
        </div>
      );
    }

    return null;
  })();

  return (
    <article className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
      {/* Шапка карточки */}
      <header className="border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-[20px] font-semibold leading-tight text-foreground">Обращение № {id}</h2>
          {getStatusBadge(status)}
        </div>
        <p className="mt-2 flex items-start gap-1.5 text-[15px] text-foreground">
          <MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          {location.address}
        </p>
        <p className="mt-1 text-[13px] text-muted-foreground">
          {SOURCE_TITLE[source] ?? source} · поступило {formatDateTime(timeline.createdAt)}
        </p>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-5 py-5">
        {/* Срок устранения: только пока дело у исполнителя */}
        {timeline.deadlineAt && status === "IN_PROGRESS" && (
          <div
            className={`flex items-center justify-between gap-4 rounded-md px-4 py-3 ${
              isExpired ? "bg-[#FCEBED]" : "bg-muted"
            }`}
          >
            <div>
              <div className="text-[13px] text-muted-foreground">До окончания срока</div>
              <div className="text-[13px] text-foreground">{slalabel}</div>
            </div>
            <div className={`text-[24px] font-semibold ${isExpired ? "text-danger" : "text-foreground"}`}>
              {formattedTime}
            </div>
          </div>
        )}

        {/* Фотофиксация */}
        <section>
          <SectionTitle
            aside={
              !media.photoAfterUrl && (
                <label className="inline-flex cursor-pointer select-none items-center gap-2 text-[13px] text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={showAiLayer}
                    onChange={(e) => setShowAiLayer(e.target.checked)}
                    className="peer sr-only"
                  />
                  <span className="relative h-5 w-9 rounded-full bg-input transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform after:content-[''] peer-checked:bg-primary peer-checked:after:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-ring/50" />
                  Разметка ИИ
                </label>
              )
            }
          >
            Фотофиксация
          </SectionTitle>

          {media.photoAfterUrl ? (
            <ImageCompareSlider beforeUrl={media.photoBeforeUrl} afterUrl={media.photoAfterUrl} />
          ) : (
            <div className="relative aspect-video overflow-hidden rounded-md bg-ink">
              <img
                src={media.photoBeforeUrl}
                alt={`Фото нарушения: ${location.address}`}
                className="pointer-events-none h-full w-full object-contain"
              />
              {showAiLayer &&
                media.boundingBoxes.map((box) => (
                  <div
                    key={box.id}
                    className="absolute border-2 border-[#EE3F58]"
                    style={{
                      left: `${box.x}%`,
                      top: `${box.y}%`,
                      width: `${box.width}%`,
                      height: `${box.height}%`,
                    }}
                  >
                    <span className="absolute -top-6 left-[-2px] whitespace-nowrap rounded-sm bg-[#BE1B33] px-1.5 py-0.5 text-[12px] text-white">
                      {box.label} · {(box.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
            </div>
          )}
        </section>

        {/* Объект и ответственность */}
        <section>
          <SectionTitle>Объект и ответственность</SectionTitle>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Field label="Контейнерная площадка">
              {kp ? (
                <>
                  {kp.code}
                  {kp.registryNumber && (
                    <span className="text-muted-foreground"> · реестр {kp.registryNumber}</span>
                  )}
                  {kp.score < 0.75 && <span className="block text-[13px] text-warning">не подтверждена</span>}
                </>
              ) : (
                <span className="text-warning">Не определена — обращение по дому</span>
              )}
            </Field>
            <Field label="Кадастровый номер участка">{location.cadastralNumber || "Не определён"}</Field>

            <Field label="Ответственные" wide>
              {responsibles.length === 0 ? (
                <span className="text-muted-foreground">Не определены</span>
              ) : (
                <ul className="mt-1 divide-y divide-border rounded-md border border-border">
                  {responsibles.map((r) => (
                    <li key={`${r.role}-${r.organization.id}`} className="px-3 py-2">
                      <div className="text-[13px] text-muted-foreground">{RESPONSIBLE_ROLE_TITLE[r.role]}</div>
                      <div className="text-[14px] font-medium text-foreground">
                        {typoQuotes(r.organization.name)}
                        <span className="font-normal text-muted-foreground">
                          {" "}· {ORGANIZATION_KIND_TITLE[r.organization.kind]}
                          {!r.confirmed && " · не подтверждено"}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Field>

            {userRole === "INSPECTOR" && (
              <>
                <Field label="Контакт исполнителя">{primary?.organization.phone || "Нет данных"}</Field>
                <Field label="Нарушений по адресу за месяц">
                  <span className={(primary?.recidivismCount ?? 0) > 2 ? "font-semibold text-danger" : undefined}>
                    {primary?.recidivismCount ?? 0}
                  </span>
                </Field>
              </>
            )}
          </dl>
        </section>

        {/* Ход дела */}
        <section>
          <SectionTitle>Ход дела</SectionTitle>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
            <Field label="Нарушение зафиксировано">{formatDateTime(timeline.createdAt)}</Field>
            {timeline.validatedAt && (
              <Field label="Уведомление направлено">{formatDateTime(timeline.validatedAt)}</Field>
            )}
            {timeline.deadlineAt && <Field label="Срок устранения">{formatDateTime(timeline.deadlineAt)}</Field>}
            {timeline.closedAt && (
              <Field label="Дело закрыто">
                <span className="text-success">{formatDateTime(timeline.closedAt)}</span>
              </Field>
            )}
          </dl>
          <IncidentAuditLog history={timeline.history} />
        </section>
      </div>

      {actions && <footer className="border-t border-border bg-muted px-5 py-4">{actions}</footer>}
    </article>
  );
};

// Карточка обращения в исполнении текущей темы стенда
export const UniversalIncidentCard: React.FC<TProps> = ({ userRole }) => {
  const theme = useStandStore((s) => s.theme);
  if (theme === "dispatch") return <DispatchCard role={userRole} />;
  if (theme === "dossier") return <DossierCard role={userRole} />;
  if (theme === "pro") return <ProCard role={userRole} />;
  return <GosCard userRole={userRole} />;
};

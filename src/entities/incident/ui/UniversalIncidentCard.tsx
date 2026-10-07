import React from "react";
import { useIncidentCard } from "../lib/useIncidentCard";
import { getStatusBadge } from "../lib/cardUtils";
import { Button } from "@/components/ui/button";
import { ImageCompareSlider } from "@/shared/components/image-slider/ImageCompareSlider";
import { IncidentAuditLog } from "./IncidentAuditLog";
import afterPhoto from '@/assets/25.jpg';

import {
  Camera,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  ArrowRightLeft,
} from "lucide-react";
import { generateKnmAct } from "../lib/generateKnmAct";
import type { UserRole } from "@/entities/user/types";

interface TProps {
  userRole: UserRole;

}

export const UniversalIncidentCard: React.FC<TProps> = ({ userRole}) => {
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

  // Если на карте ничего не выбрано — аккуратно сообщаем об этом
  if (!selectedIncident) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-slate-400 border-2 border-dashed border-slate-200 rounded-xl">
        <ShieldAlert className="w-12 h-12 mb-3 stroke-1 text-slate-300" />
        <p className="text-sm font-medium text-center">
          Выберите маркер инцидента на карте Липецка для просмотра деталей
        </p>
      </div>
    );
  }

  const { id, status, source, location, responsible, timeline, media } =
    selectedIncident;

  return (
    <div className="flex flex-col bg-white border border-slate-200 rounded-xl shadow-md overflow-hidden max-w-5xl w-full h-full text-slate-900">
      {/* ─── ШАПКА КАРТОЧКИ (Общая для всех ролей) ─── */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/50 px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Инцидент № {id}
          </span>
          {getStatusBadge(status)}
          <span className="text-xs text-slate-500 font-medium">
            Источник: <span className="font-bold text-slate-700">{source}</span>
          </span>
        </div>
        <div className="text-sm font-semibold text-slate-700 bg-white px-3 py-1 rounded-md border border-slate-100 shadow-xs flex items-center gap-2">
          📍 {location.address}
        </div>
      </div>

      {/* ─── ОСНОВНОЙ КОНТЕНТ (Сетка Tailwind v4: 12 колонок) ─── */}
      <div className="grid grid-cols-1 md:grid-cols-12 flex-1 overflow-y-auto">
        {/* ЛЕВАЯ КОЛОНКА: ИНТЕРАКТИВНЫЙ МЕДИА-ПЛЕЕР (5 колонок) */}
        <div className="md:col-span-5 p-5 border-b md:border-b-0 md:border-r border-slate-100 bg-slate-50/20 flex flex-col gap-4">
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            Ведомственная фотофиксация объекта
            </h4>

            {/* Тумблер ИИ рамок активен только если нет фотоотчета "Стало" или мы смотрим начальное состояние */}
            {!media.photoAfterUrl && (
              <label className="inline-flex items-center cursor-pointer select-none text-slate-500 hover:text-slate-700 transition-colors">
                <input
                  type="checkbox"
                  checked={showAiLayer}
                  onChange={(e) => setShowAiLayer(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="relative w-8 h-4 bg-slate-200 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:inset-s-0.5 after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-blue-600"></div>
                <span className="ms-2 text-[10px] font-bold tracking-wide uppercase">
                  Маска ИИ
                </span>
              </label>
            )}
          </div>

          {/* УСЛОВНЫЙ РЕНДЕР: Шторка сравнения ИЛИ карточка ИИ правонарушения */}
          {media.photoAfterUrl ? (
            // Если УК отчиталась — запускаем интерактивный слайдер сравнения "Было / Стало"
            <ImageCompareSlider
              beforeUrl={media.photoBeforeUrl}
              afterUrl={media.photoAfterUrl}
            />
          ) : (
            // Если инцидент новый — показываем стандартное фотофиксацию ИИ с Bounding Boxes
            <div className="relative flex-1 bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center aspect-video md:aspect-auto md:min-h-75">
              <img
                src={media.photoBeforeUrl}
                alt="Нарушение ТКО Липецк"
                className="w-full h-full object-contain pointer-events-none"
              />
              {showAiLayer &&
                media.boundingBoxes.map((box) => (
                  <div
                    key={box.id}
                    className="absolute border-2 border-red-500 bg-red-500/10 transition-all hover:bg-red-500/20 shadow-lg"
                    style={{
                      left: `${box.x}%`,
                      top: `${box.y}%`,
                      width: `${box.width}%`,
                      height: `${box.height}%`,
                    }}
                  >
                    <span className="absolute -top-5 left-0 bg-red-600 text-white text-[9px] font-bold px-1 py-0.5 rounded shadow whitespace-nowrap">
                      {box.label} ({(box.confidence * 100).toFixed(0)}%)
                    </span>
                  </div>
                ))}
            </div>
          )}
        </div>

        {/* ЦЕНТРАЛЬНАЯ КОЛОНКА: ДАННЫЕ РЕЕСТРА И ТАЙМЛАЙН (7 колонок) */}
        <div className="md:col-span-7 p-5 flex flex-col justify-between gap-6">
          <div className="flex flex-col gap-5">
            {/* Раздел Единого Реестра Объектов благоустройства Липецка */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                Информация об объекте и ответственности
              </h4>
              <div className="grid grid-cols-2 gap-4 bg-slate-50 p-3 rounded-lg border border-slate-100 text-sm">
                <div>
                  <span className="block text-xs text-slate-400 font-medium">
                    Балансодержатель земли
                  </span>
                  <span className="font-semibold text-slate-700">
                    {responsible.organizationName}
                  </span>
                </div>
                <div>
                  <span className="block text-xs text-slate-400 font-medium">
                    Кадастровый номер участка
                  </span>
                  <span className="font-mono text-xs font-semibold text-slate-600">
                    {location.cadastralNumber || "Не определен"}
                  </span>
                </div>
                {userRole === "INSPECTOR" && (
                  <>
                    <div>
                      <span className="block text-xs text-slate-400 font-medium">
                        Контакты оперативного мастера
                      </span>
                      <span className="font-medium text-slate-700">
                        {responsible.phone}
                      </span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-400 font-medium">
                        Индекс рецидивов по адресу
                      </span>
                      <span
                        className={`font-bold ${responsible.recidivismCount > 2 ? "text-rose-500" : "text-slate-700"}`}
                      >
                        ⚠️ {responsible.recidivismCount}-й раз за месяц
                      </span>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Встроенный таймлайн оперативного дела */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                Ход оперативного дела
              </h4>
              <div className="space-y-2 text-xs font-medium text-slate-600 pl-2 border-l border-slate-200">
                <div>
                  Фиксация нарушения ИИ:{" "}
                  <span className="text-slate-800 font-semibold">
                    {new Date(timeline.createdAt).toLocaleString("ru-RU")}
                  </span>
                </div>
                {timeline.validatedAt && (
                  <div>
                    Уведомление сформировано:{" "}
                    <span className="text-slate-800 font-semibold">
                      {new Date(timeline.validatedAt).toLocaleString("ru-RU")}
                    </span>
                  </div>
                )}
                {timeline.deadlineAt && status === "IN_PROGRESS" && (
                  <div className="mt-2 p-2 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between">
                    <span className="text-slate-600 font-bold text-[11px] uppercase tracking-wide">
                      {slalabel}
                    </span>
                    <span
                      className={`font-mono text-sm font-black px-2 py-0.5 rounded-sm ${
                        isExpired
                          ? "bg-rose-100 text-rose-600 animate-pulse"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {formattedTime}
                    </span>
                  </div>
                )}
                {timeline.closedAt && (
                  <div>
                    🎉 Инцидент успешно закрыт:{" "}
                    <span className="text-emerald-600 font-bold">
                      {new Date(timeline.closedAt).toLocaleString("ru-RU")}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <IncidentAuditLog history={timeline.history} />
          </div>

          {/* ─── ПРАВАЯ/НИЖНЯЯ ЗОНА: ДИНАМИЧЕСКИЕ ДЕЙСТВИЯ (ЗАВИСЯТ ОТ РОЛИ) ─── */}
          <div className="pt-4 border-t border-slate-100 flex flex-col gap-3">
            {/* СЦЕНАРИЙ 1: В системе ИНСПЕКТОР, инцидент только что найден ИИ */}
            {userRole === "INSPECTOR" && status === "NEW" && (
              <div className="flex flex-col gap-3">

                {/* 🎛️ ИНТЕЛЛЕКТУАЛЬНЫЙ БЛОК УПРАВЛЕНИЯ СРОКАМИ SLA */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-blue-50/50 p-2.5 rounded-lg border border-blue-100 w-full">
                  
                  {/* Условие А: Если это строго регламентированные источники — скрываем кнопки, выводим инфо-плашку */}
                  {source === 'DIRECT_ORDER' || source === 'GOVERNOR_PORTAL' || source === 'DELO_WEB' ? (
                    <div className="text-xs font-semibold text-blue-700 flex items-center gap-1.5 w-full">
                      <AlertTriangle className="w-4 h-4 text-blue-600 animate-pulse" />
                      <span>
                        Срок контроля установлен регламентом автоматически:{' '}
                        <span className="font-black text-blue-900 underline">
                          {source === 'DIRECT_ORDER' && '1 день (24 часа)'}
                          {source === 'GOVERNOR_PORTAL' && '3 дня (72 часа)'}
                          {source === 'DELO_WEB' && '30 дней (720 часов)'}
                        </span>
                      </span>
                    </div>
                  ) : (
                    // Условие Б: Для обычных ИИ-камер и чатов оставляем инспектору ручной выбор 24/48/72ч
                    <>
                      <span className="text-xs font-semibold text-blue-700 flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4" /> Выберите срок добровольного наведения порядка:
                      </span>
                      <div className="flex gap-1 self-end sm:self-auto">
                        {([24, 48, 72] as const).map((hours) => (
                          <button
                            key={hours}
                            type="button"
                            onClick={() => setSelectedDeadline(hours)}
                            className={`text-xs px-2.5 py-1 rounded-md font-bold transition-all border ${
                              selectedDeadline === hours
                                ? 'bg-blue-600 text-white border-slate-200 shadow-xs'
                                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                            }`}
                          >
                            {hours}ч
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <div className="flex flex-col gap-3 justify-end">
                  <Button
                    variant="outline"
                    onClick={() => rejectIncident(id)}
                    className="text-xs text-rose-600 border-rose-200 hover:bg-rose-50 h-9 font-semibold"
                  >
                    Отклонить (Ошибка ИИ)
                  </Button>
                  <Button
                    onClick={() => confirmIncident()}
                    className="bg-blue-600 hover:bg-blue-700 text-white text-xs h-9 font-bold shadow-sm"
                  >
                    Подтвердить и направить в УК
                  </Button>
                </div>
              </div>
            )}
            {/* СЦЕНАРИЙ 2: В системе МАСТЕР УК, задача находится в работе по таймеру */}
            {userRole === "UK" && status === "IN_PROGRESS" && (
              <div className="flex flex-col items-center justify-between gap-4 bg-slate-50 p-3 rounded-lg border border-slate-100 w-full">
                <span className="text-xs font-medium text-slate-500">
                  Уберите мусор в пределах зоны площадки и загрузите снимок
                  результата для закрытия задачи без штрафа.
                </span>
                <Button
                  onClick={() => submitPhotoReport(id, afterPhoto)}
                  className="w-full bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold h-9 shadow-sm flex items-center gap-1.5 whitespace-nowrap"
                >
                  <Camera className="w-4 h-4" /> Отправить фотоотчет "Стало"
                </Button>
              </div>
            )}

            {/* СЦЕНАРИЙ 3: В системе ИНСПЕКТОР, УК прислала отчет и идет верификация качества */}
            {userRole === "INSPECTOR" && status === "VERIFICATION" && (
              <div className="flex flex-col items-center justify-between gap-4 bg-purple-50/50 p-3 rounded-lg border border-purple-100 w-full h-auto">
                <span className="text-xs font-semibold text-purple-700 flex items-center gap-1.5">
                  <ArrowRightLeft className="w-4 h-4" /> Сверьте вкладки медиа
                  плеера ("Было / Стало") для верификации:
                </span>
                <div className="flex flex-col gap-2 w-full">
                  <Button
                    variant="outline"
                    onClick={() => rejectIncident(id)}
                    className="text-xs text-amber-600 border-amber-200 hover:bg-amber-50 h-9 font-semibold"
                  >
                    Доработать (Грязно)
                  </Button>
                  <Button
                    onClick={() => approveIncident(id)}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold h-9 shadow-sm flex items-center gap-1.5"
                  >
                    Принять и закрыть дело
                  </Button>
                </div>
              </div>
            )}

            {/* СЦЕНАРИЙ 4: Инцидент успешно закрыт в оперативном порядке (Все роли) */}
            {status === "CLOSED" && (
              <div className="bg-emerald-50 text-emerald-800 border border-emerald-100 p-3 rounded-lg text-xs font-bold text-center flex items-center justify-center gap-2 w-full">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" /> Нарушение
                успешно ликвидировано балансодержателем в добровольный
                оперативный срок. Дело закрыто.
              </div>
            )}

            {/* СЦЕНАРИЙ 5: Нарушение перешло в жесткий КНМ-контур ГЖИ / Минприроды */}
            {status === "KNM_ESCALATION" && (
              <div className="bg-rose-50 text-rose-900 border border-rose-100 p-3 rounded-lg text-xs font-medium flex flex-col md:flex-col md:items-center justify-between gap-3 w-full shadow-xs">
                <span>
                  ⚠️ Срок оперативного устранения просрочен. Начат сбор
                  доказательной базы для автоматической передачи пакета
                  документов в КНМ-контур ГЖИ.
                </span>
                {userRole === "INSPECTOR" && (
                  <Button
                    onClick={() => generateKnmAct(selectedIncident)} // ПРИВЯЗАЛИ ФУНКЦИЮ ТУТ!
                    className="w-auto h-auto bg-rose-600 hover:bg-rose-700 text-white font-bold py-2 text-xs text-center leading-tight shadow-sm whitespace-normal cursor-pointer transition-colors"
                  >
                    Выгрузить ПАКЕТ документов ДРТ (Акт + Предписание)
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

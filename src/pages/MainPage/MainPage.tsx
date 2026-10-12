import React, { useEffect } from "react";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { useStandStore } from "@/shared/theme/standStore";
import { StandBar } from "@/widgets/stand-bar/StandBar";
import { DispatchLayout } from "./layouts/DispatchLayout";

// Главная страница: полоса стенда сверху и «Диспетчерская» — карта на весь экран
// со стеклянными панелями.
export const MainPage: React.FC = () => {
  const mode = useStandStore((s) => s.mode);
  const selectIncident = useIncidentStore((s) => s.selectIncident);

  // Esc закрывает открытое дело
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") selectIncident(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectIncident]);

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden bg-background text-foreground" style={{ fontFamily: "var(--font-ui)" }}>
      <StandBar />
      {/* key: при смене тона раскладка и карта пересоздаются с цветами новой палитры */}
      <div key={mode} className="relative min-h-0 flex-1">
        <DispatchLayout />
      </div>
    </div>
  );
};

import React, { useEffect } from "react";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { useStandStore } from "@/shared/theme/standStore";
import { StandBar } from "@/widgets/stand-bar/StandBar";
import { GosLayout } from "./layouts/GosLayout";
import { DispatchLayout } from "./layouts/DispatchLayout";
import { DossierLayout } from "./layouts/DossierLayout";
import { ProLayout } from "./layouts/ProLayout";

// Главная страница стенда: полоса стенда сверху и раскладка выбранной темы.
// Раскладки разные по устройству, а не только по цвету: у «Диспетчерской» карта
// на весь экран, у «Досье» — газетная полоса, у «Профинструмента» — список с боковым меню.
export const MainPage: React.FC = () => {
  const theme = useStandStore((s) => s.theme);
  const mode = useStandStore((s) => s.mode);
  const selectIncident = useIncidentStore((s) => s.selectIncident);

  // Esc закрывает дело во всех темах; у «Профинструмента» своя клавиатура
  useEffect(() => {
    if (theme === "pro") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") selectIncident(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [theme, selectIncident]);

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden bg-background text-foreground" style={{ fontFamily: "var(--font-ui)" }}>
      <StandBar />
      {/* key: при смене тона раскладка и карта пересоздаются с цветами новой палитры */}
      <div key={`${theme}-${mode}`} className="relative min-h-0 flex-1">
        {theme === "dispatch" && <DispatchLayout />}
        {theme === "dossier" && <DossierLayout />}
        {theme === "pro" && <ProLayout />}
        {theme === "gos" && <GosLayout />}
      </div>
    </div>
  );
};

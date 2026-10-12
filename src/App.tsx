import { useEffect } from "react";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { MOCK_LIPETSK_INCIDENTS } from "@/entities/incident/model/mockIncidents";
import { MainPage } from "@/pages/MainPage/MainPage";

export default function App() {
  const setIncidents = useIncidentStore((state) => state.setIncidents);

  // Инициализируем стейт-менеджер изолированными mock-данными при монтировании
  useEffect(() => {
    setIncidents(MOCK_LIPETSK_INCIDENTS);
  }, [setIncidents]);

  // Шапка живёт в MainPage: она же переключает разделы
  return (
    <div className="antialiased">
      <MainPage />
    </div>
  );
}

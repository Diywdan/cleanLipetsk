import { useEffect } from "react";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { MOCK_LIPETSK_INCIDENTS } from "@/entities/incident/model/mockIncidents";
import { DEMO_INCIDENTS } from "@/entities/incident/model/demoIncidents";
import { useStandStore } from "@/shared/theme/standStore";
import { MainPage } from "@/pages/MainPage/MainPage";

export default function App() {
  const setIncidents = useIncidentStore((state) => state.setIncidents);
  const selectIncident = useIncidentStore((state) => state.selectIncident);
  const dataset = useStandStore((state) => state.dataset);

  // Набор данных стенда: расширенный условный или четыре обращения из макета
  useEffect(() => {
    setIncidents(dataset === "demo" ? DEMO_INCIDENTS : MOCK_LIPETSK_INCIDENTS);
    // Ссылка на дело: ?id=0248 открывает карточку сразу
    selectIncident(new URLSearchParams(window.location.search).get("id"));
  }, [dataset, setIncidents, selectIncident]);

  // Шапка живёт в раскладке темы: она же переключает разделы
  return (
    <div className="antialiased">
      <MainPage />
    </div>
  );
}

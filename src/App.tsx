import { useEffect } from "react";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { MOCK_LIPETSK_INCIDENTS } from "@/entities/incident/model/mockIncidents";
import { DEMO_INCIDENTS } from "@/entities/incident/model/demoIncidents";
import { DEMO_KP } from "@/entities/incident/model/demoIncidents";
import { createIncidentApi } from "@/entities/incident/api/incidentApi";
import { createKpApi } from "@/entities/kp/model/kpApi";
import { useKpStore } from "@/entities/kp/model/kpStore";
import { kpFromIncidents } from "@/entities/kp/lib/registry";
import { useStandStore } from "@/shared/theme/standStore";
import { MainPage } from "@/pages/MainPage/MainPage";

export default function App() {
  const load = useIncidentStore((state) => state.load);
  const loadKp = useKpStore((state) => state.load);
  const dataset = useStandStore((state) => state.dataset);

  // Набор данных стенда: расширенный условный или четыре обращения из макета.
  // С VITE_API_URL оба API ходят на бэкенд, и набор стенда не используется.
  useEffect(() => {
    const seed = () => (dataset === "demo" ? DEMO_INCIDENTS : MOCK_LIPETSK_INCIDENTS);
    // Ссылка на дело: ?id=0248 открывает карточку сразу
    load(createIncidentApi(dataset, seed), new URLSearchParams(window.location.search).get("id"));
    loadKp(createKpApi(() => kpFromIncidents(seed(), dataset === "demo" ? DEMO_KP : [])));
  }, [dataset, load, loadKp]);

  // Шапка живёт в раскладке темы: она же переключает разделы
  return (
    <div className="antialiased">
      <MainPage />
    </div>
  );
}

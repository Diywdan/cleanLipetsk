import { useEffect } from "react";
import { useIncidentStore } from "@/entities/incident/model/incidentStore";
import { MOCK_LIPETSK_INCIDENTS } from "@/entities/incident/model/mockIncidents";
import { DEMO_INCIDENTS } from "@/entities/incident/model/demoIncidents";
import { DEMO_KP } from "@/entities/incident/model/demoIncidents";
import { createIncidentApi } from "@/entities/incident/api/incidentApi";
import { createKpApi } from "@/entities/kp/model/kpApi";
import { useKpStore } from "@/entities/kp/model/kpStore";
import { createExecutorApi } from "@/entities/executor/model/executorApi";
import { useExecutorStore } from "@/entities/executor/model/executorStore";
import { kpFromIncidents } from "@/entities/kp/lib/registry";
import { useAuthStore } from "@/entities/user/model/authStore";
import { API_URL } from "@/shared/api/http";
import { useStandStore } from "@/shared/theme/standStore";
import { MainPage } from "@/pages/MainPage/MainPage";
import { LoginPage } from "@/pages/LoginPage/LoginPage";

// Как часто перечитывать дела из CRM: новые сообщения из бота и эскалация по сроку идут на сервере
const REFRESH_MS = 30_000;

export default function App() {
  const load = useIncidentStore((state) => state.load);
  const refresh = useIncidentStore((state) => state.refresh);
  const loadKp = useKpStore((state) => state.load);
  const loadExecutors = useExecutorStore((state) => state.load);
  const dataset = useStandStore((state) => state.dataset);
  const status = useAuthStore((state) => state.status);
  const userId = useAuthStore((state) => state.currentUser?.id);
  const role = useAuthStore((state) => state.currentUser?.role);
  const restore = useAuthStore((state) => state.restore);

  // С бэкендом сначала узнаём, есть ли сессия; на стенде пользователь известен сразу
  useEffect(() => {
    restore();
  }, [restore]);

  // Набор данных стенда: расширенный условный или четыре обращения из макета.
  // С VITE_API_URL оба API ходят на бэкенд, и набор стенда не используется.
  // Сменился пользователь — перечитываем: исполнитель видит только дела своей организации.
  useEffect(() => {
    if (status !== "ready") return;
    const seed = () => (dataset === "demo" ? DEMO_INCIDENTS : MOCK_LIPETSK_INCIDENTS);
    // Ссылка на дело: ?id=0248 открывает карточку сразу
    load(createIncidentApi(dataset, seed), new URLSearchParams(window.location.search).get("id"));
    loadKp(createKpApi(() => kpFromIncidents(seed(), dataset === "demo" ? DEMO_KP : [])));
  }, [dataset, load, loadKp, status, userId]);

  // Справочник ведомств и типов — инспектору: поправить исполнителя при подтверждении дела
  useEffect(() => {
    if (status === "ready" && role === "INSPECTOR") loadExecutors(createExecutorApi());
  }, [loadExecutors, role, status]);

  useEffect(() => {
    if (!API_URL || status !== "ready") return;
    const timer = setInterval(() => refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh, status]);

  if (status === "checking") return <div className="h-dvh bg-background" aria-busy="true" />;
  if (status === "anonymous") return <LoginPage />;

  // Шапка живёт в раскладке темы: она же переключает разделы
  return (
    <div className="antialiased">
      <MainPage />
    </div>
  );
}

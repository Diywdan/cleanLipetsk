import type {
  IBoundingBox,
  IHistoryEvent,
  IIncident,
  IncidentSource,
  IncidentStatus,
  IOrganization,
} from '../types';
import type { IKpCard } from '@/entities/kp/types';
import { MOCK_LIPETSK_INCIDENTS } from './mockIncidents';
// Условные снимки площадки (рисунок, не фото): навал слева и строительный мусор справа
import photoBefore from '@/assets/demo/kp-before.svg';
import photoAfter from '@/assets/demo/kp-after.svg';

// ─────────────────────────────────────────────────────────────────────────────
// ДЕМОНСТРАЦИОННЫЙ НАБОР ДЛЯ СТЕНДА. Данные условные: адреса, организации,
// сроки и точки на карте сгенерированы, чтобы показать дизайн на живом объёме
// (все статусы, просрочки, повторы). К реальным площадкам и УК отношения не имеют.
// Генератор детерминированный — при каждой загрузке тот же набор.
// ─────────────────────────────────────────────────────────────────────────────

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rnd = mulberry32(48);
const pick = <T,>(items: readonly T[]): T => items[Math.floor(rnd() * items.length)];
const between = (a: number, b: number) => a + rnd() * (b - a);

// Районы — прямоугольники [долгота мин, макс, широта мин, макс] и улицы в них.
const AREAS = [
  { box: [39.535, 39.572, 52.598, 52.622], upravas: [1, 2, 3], streets: ['ул. Космонавтов', 'ул. Катукова', 'ул. Стаханова', 'бул. Есенина'] },
  { box: [39.578, 39.606, 52.598, 52.618], upravas: [4, 5, 6], streets: ['ул. Советская', 'ул. Ленина', 'ул. Плеханова', 'ул. Гагарина', 'ул. Зегеля'] },
  { box: [39.558, 39.598, 52.624, 52.642], upravas: [7, 8, 9, 10], streets: ['ул. Водопьянова', 'ул. 9 Мая', 'ул. Неделина', 'ул. Жуковского'] },
  { box: [39.645, 39.672, 52.606, 52.628], upravas: [11, 12, 13, 14], streets: ['ул. Юношеская', 'ул. Краснознамённая', 'ул. Ушинского'] },
  { box: [39.542, 39.578, 52.580, 52.596], upravas: [15, 16, 17, 18, 19], streets: ['пр-кт Победы', 'ул. Московская', 'ул. Папина', 'ул. Терешковой'] },
] as const;

const UK: IOrganization[] = [
  { id: 'uk_01', name: 'УК "Левобережная"', kind: 'UK', phone: '+7 (4742) 55-12-34' },
  { id: 'uk_02', name: 'УК "Правобережная"', kind: 'UK', phone: '+7 (4742) 44-56-78' },
  { id: 'uk_03', name: 'УК "Северная"', kind: 'UK', phone: '+7 (4742) 31-20-07' },
  { id: 'uk_04', name: 'УК "Центральная"', kind: 'UK', phone: '+7 (4742) 27-11-90' },
  { id: 'mup_01', name: 'МУП "Благоустройство"', kind: 'UK', phone: '+7 (4742) 22-00-15' },
];
const REG_OPERATOR: IOrganization = {
  id: 'org_regop', name: 'ООО "ЭкоПром-Липецк"', kind: 'REG_OPERATOR', phone: '+7 (4742) 00-00-00',
};

const SOURCES: IncidentSource[] = [
  'AI_CAMERA', 'AI_CAMERA', 'AI_CAMERA', 'AI_CAMERA', 'TSUR', 'HOUSE_CHATS',
  'MAKS_CHAT', 'INSPECTION', 'GOVERNOR_PORTAL', 'DIRECT_ORDER', 'DRT_WEBSITE',
];

// Сколько обращений какого статуса и сколько из «в работе» уже просрочено
// ── Справочник площадок ─────────────────────────────────────────────────────
// Отдельный генератор, чтобы набор обращений не менялся от числа площадок.
// Обращения с КП садятся на эти площадки, причём первые — чаще: так в реестре
// видны адреса с повторными нарушениями.
const rndKp = mulberry32(4848);
const pickKp = <T,>(items: readonly T[]): T => items[Math.floor(rndKp() * items.length)];
const betweenKp = (a: number, b: number) => a + rndKp() * (b - a);
const KP_COUNT = 16;

export const DEMO_KP: IKpCard[] = Array.from({ length: KP_COUNT }, (_, n) => {
  const area = pickKp(AREAS);
  const [lonMin, lonMax, latMin, latMax] = area.box;
  const uk = pickKp(UK);
  const code = `LP-${String(120 + n * 173).padStart(6, '0')}`;
  return {
    id: `kp_${String(n + 1).padStart(3, '0')}`,
    code,
    registryNumber: `${String(3700 + n * 41).padStart(7, '0')}-48`,
    location: {
      address: `${pickKp(area.streets)}, ${Math.floor(betweenKp(1, 120))}`,
      coordinates: [betweenKp(lonMin, lonMax), betweenKp(latMin, latMax)],
      cadastralNumber: `48:20:00${Math.floor(betweenKp(1000, 4999))}:${Math.floor(betweenKp(10, 99))}`,
      upravaId: pickKp(area.upravas),
    },
    containers: { tko: Math.floor(betweenKp(2, 6)), separate: rndKp() < 0.5 ? 1 : 0, kgmBay: rndKp() < 0.4 },
    surface: pickKp(['ASPHALT', 'ASPHALT', 'CONCRETE', 'SOIL'] as const),
    fenced: rndKp() < 0.7,
    responsibles: [
      { role: 'site_maintenance', organization: uk, confirmed: rndKp() > 0.2 },
      { role: 'waste_removal', organization: REG_OPERATOR, confirmed: true },
    ],
    dataSource: pickKp(['FGIS_UTKO', 'FGIS_UTKO', 'FIELD_CHECK'] as const),
    checkedAt: new Date(Date.now() - betweenKp(5, 120) * 86_400_000).toISOString(),
  };
});
// Чаще всего нарушения на первых площадках списка
const siteFor = () => DEMO_KP[Math.floor(rndKp() ** 1.3 * KP_COUNT)];

const PLAN: { status: IncidentStatus; count: number; overdue?: number }[] = [
  { status: 'NEW', count: 7 },
  { status: 'IN_PROGRESS', count: 10, overdue: 3 },
  { status: 'VERIFICATION', count: 4 },
  { status: 'KNM_ESCALATION', count: 4 },
  { status: 'CLOSED', count: 7 },
];

const HOUR = 60 * 60 * 1000;
const NOW = Date.now();
const iso = (ms: number) => new Date(ms).toISOString();

function boxes(): IBoundingBox[] {
  const n = rnd() < 0.6 ? 1 : 2;
  return Array.from({ length: n }, (_, i) => ({
    id: `b${i}`,
    // слева на рисунке бытовой навал, справа — строительный мусор
    label: i === 0 ? pick(['Навал КГМ', 'Мусор вне площадки', 'Переполнение ТКО'] as const) : 'Строительный мусор',
    confidence: Math.round(between(0.78, 0.98) * 100) / 100,
    // рамки ложатся на навалы рисунка kp-before.svg
    x: i === 0 ? Math.round(between(5, 9)) : Math.round(between(61, 64)),
    y: Math.round(between(53, 58)),
    width: i === 0 ? Math.round(between(24, 28)) : Math.round(between(24, 27)),
    height: Math.round(between(20, 25)),
  }));
}

function build(): IIncident[] {
  const out: IIncident[] = [];
  let seq = 101;

  for (const { status, count, overdue = 0 } of PLAN) {
    for (let i = 0; i < count; i++) {
      const area = pick(AREAS);
      const [lonMin, lonMax, latMin, latMax] = area.box;
      const street = pick(area.streets);
      const house = Math.floor(between(1, 120));
      const uk = pick(UK);
      const source = pick(SOURCES);
      const id = String(seq++).padStart(4, '0');
      const viol = boxes();
      const isOverdue = status === 'IN_PROGRESS' && i < overdue;

      // Время: новые — последние сутки, в работе — до недели, закрытые — до двух недель назад
      const created = NOW - (status === 'NEW' ? between(0.3, 20) : status === 'CLOSED' ? between(30, 330) : between(20, 160)) * HOUR;
      const validated = created + between(0.5, 5) * HOUR;
      const hours = pick([24, 48, 72] as const);
      let deadline = validated + hours * HOUR;
      if (status === 'IN_PROGRESS') {
        // просроченные — срок вышел 1–10 ч назад; остальные — ещё идут
        deadline = isOverdue ? NOW - between(1, 10) * HOUR : NOW + between(2, 60) * HOUR;
      }
      if (status === 'KNM_ESCALATION') deadline = NOW - between(6, 40) * HOUR;
      const closed = status === 'CLOSED' ? Math.min(deadline - between(2, 20) * HOUR, NOW - HOUR) : undefined;

      const history: IHistoryEvent[] = [
        {
          id: 'h1',
          timestamp: iso(created),
          title: source === 'AI_CAMERA' ? 'Обнаружено нарушение ИИ' : 'Поступило обращение',
          description: `${viol.map((b) => b.label).join(', ')}. Адрес: ${street}, ${house}.`,
          type: source === 'AI_CAMERA' ? 'AI' : 'SYSTEM',
        },
      ];
      if (status !== 'NEW') {
        history.push({
          id: 'h2',
          timestamp: iso(validated),
          title: 'Нарушение подтверждено',
          description: `Инспектор направил уведомление в ${uk.name}, срок ${hours} ч.`,
          type: 'INSPECTOR',
        });
      }
      if (status === 'VERIFICATION' || status === 'CLOSED') {
        history.push({
          id: 'h3',
          timestamp: iso((closed ?? NOW - between(1, 6) * HOUR) - HOUR),
          title: 'Фотоотчёт исполнителя',
          description: 'Исполнитель приложил снимок убранной площадки.',
          type: 'UK',
        });
      }
      if (status === 'CLOSED') {
        history.push({ id: 'h4', timestamp: iso(closed!), title: 'Дело закрыто', description: 'Инспектор принял работу.', type: 'INSPECTOR' });
      }
      if (status === 'KNM_ESCALATION') {
        history.push({ id: 'h4', timestamp: iso(deadline), title: 'Срок истёк', description: 'Материалы переданы на контрольно-надзорное мероприятие.', type: 'SYSTEM' });
      }

      const hasKp = rnd() > 0.18;
      const site = hasKp ? siteFor() : null;
      const kpScore = Math.round(between(0.6, 1) * 100) / 100;
      const kpMethod = pick(['explicit', 'registry_house', 'nearest_single', 'nearest_multi'] as const);
      const coords: [number, number] = [between(lonMin, lonMax), between(latMin, latMax)];
      const cadastral = `48:20:00${Math.floor(between(1000, 4999))}:${Math.floor(between(10, 99))}`;
      const executor = site ? site.responsibles[0].organization : uk;
      if (site) {
        // Текст хроники ссылается на адрес — обновляем на адрес площадки
        history[0].description = `${viol.map((b) => b.label).join(', ')}. Адрес: ${site.location.address}.`;
        if (history[1]) history[1].description = `Инспектор направил уведомление в ${executor.name}, срок ${hours} ч.`;
      }
      out.push({
        id,
        status,
        source,
        priority: source === 'DIRECT_ORDER' || source === 'GOVERNOR_PORTAL' ? 'HIGH' : pick(['LOW', 'MEDIUM', 'MEDIUM', 'HIGH'] as const),
        location: site
          ? { ...site.location }
          : { address: `${street}, ${house}`, coordinates: coords, cadastralNumber: cadastral, upravaId: pick(area.upravas) },
        kp: site
          ? { kpId: site.id, code: site.code, registryNumber: site.registryNumber, score: kpScore, method: kpMethod }
          : null,
        responsibles: [
          { role: 'site_maintenance', organization: executor, confirmed: rnd() > 0.2, recidivismCount: Math.floor(rnd() ** 2 * 6) },
          { role: 'waste_removal', organization: REG_OPERATOR, confirmed: true, recidivismCount: 0 },
        ],
        timeline: {
          createdAt: iso(created),
          validatedAt: status === 'NEW' ? undefined : iso(validated),
          deadlineAt: status === 'NEW' ? undefined : iso(deadline),
          closedAt: closed ? iso(closed) : undefined,
          history,
        },
        media: {
          photoBeforeUrl: photoBefore,
          photoAfterUrl: status === 'VERIFICATION' || status === 'CLOSED' ? photoAfter : undefined,
          boundingBoxes: viol,
        },
      });
    }
  }
  return out;
}

// Сначала обращения из макета Оксаны, затем условные — по времени поступления
// Обращения из макета — с теми же условными снимками, чтобы набор выглядел единообразно
const fromMock: IIncident[] = MOCK_LIPETSK_INCIDENTS.map((i) => ({
  ...i,
  media: { ...i.media, photoBeforeUrl: photoBefore, photoAfterUrl: i.media.photoAfterUrl ? photoAfter : undefined },
}));

export const DEMO_INCIDENTS: IIncident[] = [...fromMock, ...build()].sort(
  (a, b) => new Date(b.timeline.createdAt).getTime() - new Date(a.timeline.createdAt).getTime(),
);

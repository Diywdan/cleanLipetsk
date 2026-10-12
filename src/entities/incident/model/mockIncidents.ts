import type { IIncident } from "../types";

import photoBefore from "@/assets/24.jpg";
import photoAfter from "@/assets/25.jpg";

export const MOCK_LIPETSK_INCIDENTS: IIncident[] = [
  {
    id: "0248",
    status: "NEW",
    source: "AI_CAMERA",
    priority: "HIGH",
    location: {
      address: "ул. Космонавтов, 41",
      coordinates: [39.5532, 52.6145],
      cadastralNumber: "48:20:002148:12",
      upravaId: 3
    },
    kp: {
      kpId: "kp_0001",
      code: "LP-000123",
      registryNumber: "0003709-48",
      score: 1.0,
      method: "explicit",
    },
    edsTheme: { code: "14:434135041", title: "Состояние КП" },
    responsibles: [
      {
        role: "site_maintenance",
        organization: {
          id: "uk_01",
          name: 'УК "Левобережная"',
          kind: "UK",
          directorName: "Иванов И.И.",
          phone: "+7 (4742) 55-12-34",
          email: "info@levber.ru",
        },
        confirmed: true,
        recidivismCount: 3,
      },
      {
        role: "waste_removal",
        organization: {
          id: "org_regop",
          name: 'ООО "ЭкоПром-Липецк"',
          kind: "REG_OPERATOR",
          phone: "+7 (4742) 00-00-00",
        },
        confirmed: true,
        recidivismCount: 0,
      },
    ],
    timeline: {
      createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      history: [
        {
          id: "h1",
          timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
          title: "Обнаружено нарушение ИИ",
          description:
            "ИИ-камера зафиксировала навал КГМ (Диван) и переполнение ТКО. Точность 94%.",
          type: "AI",
        },
        {
          id: "h2",
          timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
          title: "Инцидент зарегистрирован",
          description:
            "Кейс поставлен на первичный учет ведомственного контроля ДРТ.",
          type: "SYSTEM",
        },
      ],
    },
    media: {
      photoBeforeUrl: photoBefore,
      photoAfterUrl: photoAfter,
      boundingBoxes: [
        {
          id: "box_1",
          label: "Навал КГМ (Диван)",
          confidence: 0.94,
          x: 20,
          y: 35,
          width: 45,
          height: 50,
        },
        {
          id: "box_2",
          label: "Переполнение ТКО",
          confidence: 0.88,
          x: 70,
          y: 20,
          width: 22,
          height: 40,
        },
      ],
    },
  },
  {
    id: "0247",
    status: "IN_PROGRESS",
    source: "TSUR",
    priority: "MEDIUM",
    location: {
      address: "пр-кт Победы, 102",
      coordinates: [39.5615, 52.5931],
      cadastralNumber: "48:20:003501:44",
      upravaId: 5,
      houseFias: "00000000-0000-0000-0000-000000000247",
    },
    kp: null,
    edsTheme: { code: "14:463369040", title: "Мусор вокруг КП" },
    responsibles: [
      {
        role: "site_maintenance",
        organization: {
          id: "uk_02",
          name: 'УК "Правобережная"',
          kind: "UK",
          directorName: "Петров П.П.",
          phone: "+7 (4742) 44-56-78",
          email: "contact@pravber.ru",
        },
        confirmed: false,
        recidivismCount: 1,
      },
      {
        role: "waste_removal",
        organization: {
          id: "org_regop",
          name: 'ООО "ЭкоПром-Липецк"',
          kind: "REG_OPERATOR",
          phone: "+7 (4742) 00-00-00",
        },
        confirmed: true,
        recidivismCount: 0,
      },
    ],
    timeline: {
      createdAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      validatedAt: new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString(),
      deadlineAt: new Date(Date.now() + 25 * 60 * 60 * 1000).toISOString(),
      history: [
        {
          id: 'h3',
          timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
          title: 'Обращение из ЦУР',
          description: 'Сигнал о крупногабаритном мусоре поступил из систем обратной связи жителей.',
          type: 'SYSTEM'
        },
        {
          id: 'h4',
          timestamp: new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString(),
          title: 'Уведомление подтверждено ДРТ',
          description: 'Инспектор ДРТ верифицировал фото нарушения и направил предписание в УК.',
          type: 'INSPECTOR'
        },
        {
          id: 'h5',
          timestamp: new Date(Date.now() - 22 * 60 * 60 * 1000).toISOString(),
          title: 'В работе у балансодержателя',
          description: 'УК "Правобережная" приняла задачу на приведение контейнерной площадки в порядок.',
          type: 'UK'
        }
      ]
    },
    media: {
      photoBeforeUrl: photoBefore,
      photoAfterUrl: photoAfter,
      boundingBoxes: [
        {
          id: "box_3",
          label: "Крупногабаритный мусор",
          confidence: 0.91,
          x: 30,
          y: 40,
          width: 35,
          height: 45,
        },
      ],
    },
  },
  {
    id: "0100",
    status: "IN_PROGRESS",
    source: "AI_CAMERA",
    priority: "HIGH",
    location: {
      address: "ул. Зегеля, 2",
      coordinates: [39.5992, 52.6111],
      cadastralNumber: "48:20:001102:05",
      upravaId: 3
    },
    kp: {
      kpId: "kp_0002",
      code: "LP-000456",
      registryNumber: "0004120-48",
      score: 0.9,
      method: "registry_house",
    },
    edsTheme: { code: "14:463369040", title: "Мусор вокруг КП" },
    responsibles: [
      {
        role: "site_maintenance",
        organization: {
          id: "uk_01",
          name: 'УК "Левобережная"',
          kind: "UK",
          directorName: "Иванов И.И.",
          phone: "+7 (4742) 55-12-34",
          email: "info@levber.ru",
        },
        confirmed: true,
        recidivismCount: 5,
      },
      {
        role: "waste_removal",
        organization: {
          id: "org_regop",
          name: 'ООО "ЭкоПром-Липецк"',
          kind: "REG_OPERATOR",
          phone: "+7 (4742) 00-00-00",
        },
        confirmed: true,
        recidivismCount: 0,
      },
    ],
    timeline: {
      createdAt: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
      validatedAt: new Date(Date.now() - 9 * 60 * 1000).toISOString(),
      deadlineAt: new Date(Date.now() + 15000).toISOString(),
    },
    media: {
      photoBeforeUrl: photoBefore,
      boundingBoxes: [
        {
          id: "box_9",
          label: "Строительный мусор",
          confidence: 0.96,
          x: 10,
          y: 15,
          width: 80,
          height: 70,
        },
      ],
    },
  },
  {
    id: '0999',
    status: 'NEW',
    source: 'DIRECT_ORDER', 
    priority: 'HIGH', 
    location: {
      address: 'ул. Советская, 3 (Площадка у Администрации)',
      coordinates: [39.5925, 52.6032],
      cadastralNumber: '48:20:001101:01',
      upravaId: 2
    },
    kp: {
      kpId: "kp_0003",
      code: "LP-000789",
      registryNumber: "0001544-48",
      score: 1.0,
      method: "explicit",
    },
    edsTheme: { code: "14:434135041", title: "Состояние КП" },
    responsibles: [
      {
        role: "site_maintenance",
        organization: {
          id: "omsu_01",
          name: 'МУП "Благоустройство"',
          kind: "OMSU",
          directorName: "Сергеев С.С.",
          phone: "+7 (4742) 11-22-33",
          email: "mup@lipetsk.ru",
        },
        confirmed: true,
        recidivismCount: 0,
      },
      {
        role: "waste_removal",
        organization: {
          id: "org_regop",
          name: 'ООО "ЭкоПром-Липецк"',
          kind: "REG_OPERATOR",
          phone: "+7 (4742) 00-00-00",
        },
        confirmed: true,
        recidivismCount: 0,
      },
    ],
    timeline: {
      createdAt: new Date().toISOString(),
      validatedAt: new Date().toISOString(),
      deadlineAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), 
      history: [
        {
          id: 'h99',
          timestamp: new Date().toISOString(),
          title: 'Получено прямое поручение Председателя ДРТ',
          description: 'Поручение с выездного совещания. Требуется незамедлительная очистка территории в течение 24 часов.',
          type: 'SYSTEM'
        }
      ]
    },
    media: {
      photoBeforeUrl: photoBefore,
      boundingBoxes: [{ id: 'box_critical', label: 'Навал строительных отходов', confidence: 0.99, x: 15, y: 20, width: 70, height: 60 }]
    }
  }
];

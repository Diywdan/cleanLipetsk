"""reference data

Справочники, извлечённые из реальных форм и инструкции по пакету документов.
Идемпотентна: повторный запуск не создаёт дублей.

Revision ID: seed0001
Revises: 943f2b998f61
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "seed0001"
down_revision: Union[str, None] = "943f2b998f61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CODE_TABLES = {
    "roles": [
        ("administrator", "Администратор", "Полный доступ к системе"),
        ("manager", "Руководитель", "Утверждение заданий и решений"),
        ("inspector", "Инспектор", "Проведение мероприятий и подготовка документов"),
        ("observer", "Наблюдатель", "Только просмотр"),
    ],
    "control_kinds": [
        (
            "municipal_improvement",
            "Муниципальный контроль в сфере благоустройства на территории города Липецка",
        ),
    ],
    "control_case_statuses": [
        ("draft", "Черновик"),
        ("planned", "Запланировано"),
        ("in_progress", "Проводится"),
        ("completed", "Завершено"),
        ("cancelled", "Отменено"),
    ],
    "prescription_statuses": [
        ("primary", "Первичное"),
        ("repeated", "Повторное"),
        ("executed", "Исполнено"),
        ("not_executed", "Не исполнено"),
        ("extended", "Срок продлён"),
        ("appealed", "Обжаловано"),
        ("cancelled", "Отменено"),
    ],
    "document_statuses": [
        ("draft", "Черновик"),
        ("generated", "Сформирован"),
        ("signed", "Подписан"),
        ("sent", "Отправлен"),
        ("cancelled", "Отменён"),
    ],
    "package_kinds": [
        ("primary_prescription", "Первичное предписание"),
        ("repeated_prescription", "Повторное предписание"),
        ("executed_prescription", "Исполненное предписание"),
    ],
    "control_object_types": [
        ("apartment_building", "Многоквартирный дом"),
        ("land_plot", "Земельный участок"),
        ("building", "Здание"),
        ("construction", "Сооружение"),
        ("improvement_element", "Элемент благоустройства"),
        ("social_infrastructure", "Объект социальной инфраструктуры"),
        ("entrance_group", "Входная группа"),
        ("information_element", "Информационный элемент"),
        ("container_site", "Контейнерная площадка"),
        ("container", "Контейнер"),
    ],
    "appeal_sources": [
        ("oral_citizen", "Устное обращение жителя"),
        ("written_citizen", "Письменное обращение жителя"),
        (
            "mu_material",
            "Материал МУ «Управление главного смотрителя г. Липецка»",
        ),
        ("prosecutor", "Требование (обращение) прокуратуры"),
        ("portal", "Портал / государственная информационная система"),
        ("other", "Иное"),
    ],
    "violation_types": [
        ("container_overflow", "Переполнение контейнерной площадки"),
        (
            "untimely_waste_removal",
            "Несвоевременный вывоз твёрдых коммунальных отходов",
        ),
        ("waste_piles", "Навалы мусора на территории"),
        (
            "unrestored_improvement",
            "Невосстановленное благоустройство после земляных работ",
        ),
        ("territory_maintenance", "Ненадлежащее содержание территории"),
    ],
}


DOCUMENT_TYPES = [
    ("assignment", "Задание на проведение выездного обследования", False, 1),
    ("act", "Акт выездного обследования", True, 2),
    ("inspection_protocol", "Протокол осмотра", False, 3),
    ("decision", "Решение по результатам контрольного мероприятия", True, 4),
    ("prescription", "Предписание об устранении нарушения", True, 5),
    ("direction", "Направление предписания", False, 6),
    (
        "appearance_notice",
        "Уведомление о явке для составления протокола об административном правонарушении",
        False,
        7,
    ),
    (
        "administrative_protocol",
        "Протокол об административном правонарушении",
        False,
        8,
    ),
]


CONTROL_FORMS = [
    ("field_survey", "Выездное обследование", True, 1),
    ("inspection_visit", "Инспекционный визит", False, 2),
    ("documentary_check", "Документарная проверка", False, 3),
    ("field_check", "Выездная проверка", False, 4),
]


# Состав пакетов по инструкции: первичный — 6 документов, повторный — те же
# плюс уведомление о явке и протокол об АП, исполненный — три документа.
PACKAGE_COMPOSITION = [
    ("primary_prescription", "assignment", 1),
    ("primary_prescription", "act", 2),
    ("primary_prescription", "inspection_protocol", 3),
    ("primary_prescription", "decision", 4),
    ("primary_prescription", "prescription", 5),
    ("primary_prescription", "direction", 6),
    ("repeated_prescription", "assignment", 1),
    ("repeated_prescription", "act", 2),
    ("repeated_prescription", "inspection_protocol", 3),
    ("repeated_prescription", "decision", 4),
    ("repeated_prescription", "prescription", 5),
    ("repeated_prescription", "direction", 6),
    ("repeated_prescription", "appearance_notice", 7),
    ("repeated_prescription", "administrative_protocol", 8),
    ("executed_prescription", "assignment", 1),
    ("executed_prescription", "inspection_protocol", 2),
    ("executed_prescription", "act", 3),
]


NPA = [
    (
        "rules",
        "Правила благоустройства территорий города Липецка",
        "836",
        "2024-11-28",
        "Липецкий городской Совет депутатов",
    ),
    (
        "federal_law",
        "О государственном контроле (надзоре) и муниципальном контроле "
        "в Российской Федерации",
        "248-ФЗ",
        "2020-07-31",
        "Государственная Дума Федерального Собрания Российской Федерации",
    ),
    (
        "code",
        "Кодекс Российской Федерации об административных правонарушениях",
        "195-ФЗ",
        "2001-12-30",
        "Государственная Дума Федерального Собрания Российской Федерации",
    ),
]


# Квалификация нарушений и ссылки на основания — ровно те, что встречаются
# в разобранных формах предписания и решения.
NPA_ARTICLES = [
    ("836", "5", "5", "5.2", "пункт 5.2 части 5 статьи 5", "2024-11-28"),
    ("836", "14", "7", None, "часть 7 статьи 14", "2024-11-28"),
    ("836", "14", "12", None, "часть 12 статьи 14", "2024-11-28"),
    ("248-ФЗ", "75", None, None, "статья 75", "2020-07-31"),
    ("248-ФЗ", "90", None, None, "статья 90", "2020-07-31"),
    ("195-ФЗ", "19.5", "1", None, "часть 1 статьи 19.5", "2001-12-30"),
]


CONTROL_BODY_NAME = (
    "Департамент развития территории администрации города Липецка"
)
CONTROL_BODY_ADDRESS = "Советская ул., д.68, г.Липецк, 398001"
CONTROL_BODY_UNIT = "Управление муниципального контроля"


def _seed_code_tables() -> None:
    for table, rows in CODE_TABLES.items():
        if table == "roles":
            columns = "(code, name, description)"
            values = ", ".join(
                "('{code}', '{name}', '{desc}')".format(
                    code=code.replace("'", "''"),
                    name=name.replace("'", "''"),
                    desc=(desc or "").replace("'", "''"),
                )
                for code, name, desc in rows
            )
        else:
            columns = "(code, name)"
            values = ", ".join(
                "('{code}', '{name}')".format(
                    code=code.replace("'", "''"),
                    name=name.replace("'", "''"),
                )
                for code, name in rows
            )

        op.execute(
            f"INSERT INTO {table} {columns} VALUES {values} "
            f"ON CONFLICT (code) DO NOTHING"
        )


def upgrade() -> None:
    _seed_code_tables()

    op.execute(
        "INSERT INTO control_forms "
        "(code, name, is_without_interaction, sort_order, created_at, updated_at) "
        "VALUES "
        + ", ".join(
            "('{code}', '{name}', {flag}, {sort}, now(), now())".format(
                code=code,
                name=name.replace("'", "''"),
                flag="true" if flag else "false",
                sort=sort,
            )
            for code, name, flag, sort in CONTROL_FORMS
        )
        + " ON CONFLICT (code) DO NOTHING"
    )

    op.execute(
        "INSERT INTO document_types "
        "(code, name, uses_external_number, sort_order, created_at, updated_at) "
        "VALUES "
        + ", ".join(
            "('{code}', '{name}', {ext}, {sort}, now(), now())".format(
                code=code,
                name=name.replace("'", "''"),
                ext="true" if ext else "false",
                sort=sort,
            )
            for code, name, ext, sort in DOCUMENT_TYPES
        )
        + " ON CONFLICT (code) DO NOTHING"
    )

    op.execute(
        "INSERT INTO package_kind_documents "
        "(package_kind_id, document_type_id, sequence_no, is_required) "
        "SELECT pk.id, dt.id, v.seq, true "
        "FROM (VALUES "
        + ", ".join(
            "('{pk}', '{dt}', {seq})".format(pk=pk, dt=dt, seq=seq)
            for pk, dt, seq in PACKAGE_COMPOSITION
        )
        + ") AS v(pk_code, dt_code, seq) "
        "JOIN package_kinds pk ON pk.code = v.pk_code "
        "JOIN document_types dt ON dt.code = v.dt_code "
        "ON CONFLICT (package_kind_id, document_type_id) DO NOTHING"
    )

    op.execute(
        "INSERT INTO npa (kind, title, number, adopted_on, adopted_by, is_active, created_at, updated_at) "
        "SELECT v.kind, v.title, v.number, v.adopted_on::date, v.adopted_by, true, now(), now() "
        "FROM (VALUES "
        + ", ".join(
            "('{kind}', '{title}', '{number}', '{adopted}', '{by}')".format(
                kind=kind,
                title=title.replace("'", "''"),
                number=number,
                adopted=adopted,
                by=by.replace("'", "''"),
            )
            for kind, title, number, adopted, by in NPA
        )
        + ") AS v(kind, title, number, adopted_on, adopted_by) "
        "WHERE NOT EXISTS (SELECT 1 FROM npa n WHERE n.number = v.number)"
    )

    op.execute(
        "INSERT INTO npa_articles "
        "(npa_id, article_number, part_number, point_number, reference_template, "
        " valid_from, created_at, updated_at) "
        "SELECT n.id, v.article_number, v.part_number, v.point_number, "
        "       v.reference_template, v.valid_from::date, now(), now() "
        "FROM (VALUES "
        + ", ".join(
            "('{number}', '{article}', {part}, {point}, '{template}', '{valid}')".format(
                number=number,
                article=article,
                part="NULL::varchar" if part is None else f"'{part}'",
                point="NULL::varchar" if point is None else f"'{point}'",
                template=template.replace("'", "''"),
                valid=valid,
            )
            for number, article, part, point, template, valid in NPA_ARTICLES
        )
        + ") AS v(npa_number, article_number, part_number, point_number, "
        "reference_template, valid_from) "
        "JOIN npa n ON n.number = v.npa_number "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM npa_articles a "
        "  WHERE a.npa_id = n.id AND a.reference_template = v.reference_template "
        "    AND a.valid_to IS NULL)"
    )

    op.execute(
        "INSERT INTO addresses "
        "(full_address, locality, street, house, postal_code, created_at, updated_at) "
        f"SELECT '{CONTROL_BODY_ADDRESS}', 'г. Липецк', 'Советская ул.', '68', '398001', "
        "now(), now() "
        f"WHERE NOT EXISTS (SELECT 1 FROM addresses WHERE full_address = '{CONTROL_BODY_ADDRESS}')"
    )

    op.execute(
        "INSERT INTO control_bodies "
        "(name, full_name, address_id, phone, email, is_active, created_at, updated_at) "
        f"SELECT '{CONTROL_BODY_NAME}', '{CONTROL_BODY_NAME}', a.id, "
        "'(4742) 22 13 30', 'depterr@lipetskcity.ru', true, now(), now() "
        f"FROM addresses a WHERE a.full_address = '{CONTROL_BODY_ADDRESS}' "
        f"AND NOT EXISTS (SELECT 1 FROM control_bodies b WHERE b.name = '{CONTROL_BODY_NAME}')"
    )

    op.execute(
        "INSERT INTO control_body_units "
        "(control_body_id, name, is_active, created_at, updated_at) "
        f"SELECT b.id, '{CONTROL_BODY_UNIT}', true, now(), now() "
        f"FROM control_bodies b WHERE b.name = '{CONTROL_BODY_NAME}' "
        "ON CONFLICT (control_body_id, name) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM control_body_units WHERE name = '{}'".format(CONTROL_BODY_UNIT)
    )
    op.execute(
        "DELETE FROM control_bodies WHERE name = '{}'".format(CONTROL_BODY_NAME)
    )
    op.execute(
        "DELETE FROM addresses WHERE full_address = '{}' "
        "AND NOT EXISTS (SELECT 1 FROM control_bodies b WHERE b.address_id = addresses.id) "
        "AND NOT EXISTS (SELECT 1 FROM organization_units u WHERE u.address_id = addresses.id) "
        "AND NOT EXISTS (SELECT 1 FROM control_objects o WHERE o.address_id = addresses.id) "
        "AND NOT EXISTS (SELECT 1 FROM control_actions a WHERE a.place_address_id = addresses.id) "
        "AND NOT EXISTS (SELECT 1 FROM appeals ap WHERE ap.address_id = addresses.id) "
        "AND NOT EXISTS (SELECT 1 FROM violations v WHERE v.address_id = addresses.id)".format(
            CONTROL_BODY_ADDRESS
        )
    )

    op.execute(
        "DELETE FROM npa_articles a USING npa n "
        "WHERE a.npa_id = n.id AND n.number IN ('836', '248-ФЗ', '195-ФЗ')"
    )
    op.execute("DELETE FROM npa WHERE number IN ('836', '248-ФЗ', '195-ФЗ')")

    op.execute(
        "DELETE FROM package_kind_documents pd USING package_kinds pk "
        "WHERE pd.package_kind_id = pk.id "
        "AND pk.code IN ('primary_prescription', 'repeated_prescription', "
        "'executed_prescription')"
    )

    for table in (
        "document_types",
        "package_kinds",
        "control_forms",
        "control_kinds",
        "control_case_statuses",
        "prescription_statuses",
        "document_statuses",
        "control_object_types",
        "appeal_sources",
        "violation_types",
        "roles",
    ):
        codes = [row[0] for row in CODE_TABLES.get(table, [])]
        if table == "document_types":
            codes = [row[0] for row in DOCUMENT_TYPES]
        elif table == "control_forms":
            codes = [row[0] for row in CONTROL_FORMS]
        if not codes:
            continue
        quoted = ", ".join("'{}'".format(code) for code in codes)
        op.execute(f"DELETE FROM {table} WHERE code IN ({quoted})")

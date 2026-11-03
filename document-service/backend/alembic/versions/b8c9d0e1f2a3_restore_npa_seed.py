"""Справочник норм: восстановить пропущенное наполнение

В справочнике норм оказались только три акта и шесть норм, а связей «вид
нарушения — норма» не было вовсе. Из-за этого в форме заявки список норм
был пустым: фильтр по виду нарушения не находил ни одной связанной нормы.

Миграция наполнения (a3b4c5d6e7f8) в истории есть, но её данных в базе нет —
восстанавливаем их этой миграцией. Она ничего не удаляет и не перезаписывает:

* акт «Правила благоустройства…» берётся существующий (или заводится, если
  его нет);
* нормы добавляются только те, которых нет, по тройке «статья, часть, пункт»;
* связи «вид нарушения — норма» добавляются заново, повторы пропускаются.

Поэтому уже выбранные у нарушений нормы остаются теми же записями.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-27 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACT_TITLE = "Правила благоустройства территорий города Липецка"
ACT_GENITIVE = "Правил благоустройства территорий города Липецка"
ADOPTED_ON = "2024-11-28"
VALID_FROM = "2025-03-01"
# (номер статьи, название)
ARTICLES: list[tuple[str, str]] = [
    ("1", "Общие положения"),
    ("2", "Основные понятия, используемые в Правилах"),
    ("3", "Содержание территорий общего пользования и порядок пользования такими территориями"),
    ("4", "Требования к внешнему виду фасадов и ограждающих конструкций зданий, строений, сооружений"),
    ("5", "Требования по проектированию, размещению, содержанию и восстановлению элементов благоустройства, в том числе после проведения земляных работ"),
    ("6", "Требования по организации освещения территории города Липецка"),
    ("7", "Организация озеленения территории города Липецка"),
    ("8", "Размещение информации на территории города Липецка"),
    ("9", "Размещение и содержание детских и спортивных площадок, площадок для выгула животных, парковок, МАФ"),
    ("10", "Организация пешеходных коммуникаций"),
    ("11", "Обустройство территории для беспрепятственного передвижения инвалидов и МГН"),
    ("12", "Уборка территории города Липецка, в том числе в зимний период"),
    ("13", "Организация стоков ливневых вод"),
    ("14", "Порядок проведения земляных работ"),
    ("15", "Порядок участия собственников в содержании прилегающих территорий"),
    ("16", "Определение границ прилегающих территорий"),
    ("17", "Праздничное оформление территории города Липецка"),
    ("18", "Порядок участия граждан и организаций в благоустройстве"),
    ("19", "Формы и механизмы общественного участия"),
    ("20", "Вступление в силу и действие Правил"),
]

# (статья, часть, пункт, краткое содержание)
PARTS: list[tuple[str, str, str | None, str]] = [
    ("3", "1", None, "содержание территорий общего пользования"),
    ("3", "2", None, "участие собственников в содержании прилегающих территорий"),
    ("4", "2", None, "содержание фасада, очистка от снега, льда и сосулек"),
    ("4", "2.1", None, "запрет надписей, рисунков, объявлений на фасадах"),
    ("4", "2.3", None, "устранение повреждений фасада, включая надписи и рисунки"),
    ("4", "2.5", None, "запреты на нанесение изображений на фасады"),
    ("5", "3", "3.1", "согласование создания площадки накопления ТКО"),
    ("5", "3", "3.2", "требования к площадке: контейнеры, подъезды, доступность МГН"),
    ("5", "3", "3.3", "содержание площадки ТКО и территории по периметру 10 м"),
    ("5", "3", "3.4", "договоры с региональным оператором"),
    ("5", "3", "3.5", "запрет размещения отходов вне площадок"),
    ("5", "3", "3.6", "обустройство площадки: покрытие, уклон, ограждение"),
    ("5", "3", "3.7", "содержание территории площадки, нарушение графика вывоза"),
    ("5", "5", "5.1", "осмотр элементов благоустройства, уход за газонами"),
    ("5", "5", "5.2", "восстановление элементов благоустройства, в том числе после земляных работ"),
    ("5", "6", None, "запреты при содержании территорий и элементов благоустройства"),
    ("6", "9", None, "режим работы наружного освещения по суточному графику"),
    ("6", "10", None, "освещение дворов и местных дорог"),
    ("6", "11", None, "содержание, эксплуатация и ремонт сетей наружного освещения"),
    ("7", "1", None, "содержание элементов озеленения (кроме участков ИЖС)"),
    ("8", "2", None, "запрет самовольных рисунков и надписей на зданиях и в подъездах"),
    ("9", "3", None, "содержание детских и спортивных площадок"),
    ("10", "1", None, "проектирование и содержание пешеходных коммуникаций"),
    ("12", "2", None, "режимы уборки проезжей части, тротуаров, придомовых территорий"),
    ("12", "3", None, "зимний период уборки"),
    ("12", "4", None, "зимняя уборка: снег, наледь, сосульки, обработка"),
    ("12", "5", None, "летняя уборка: дороги, тротуары, мусор, покос газонов"),
    ("13", "3", None, "содержание и ремонт сетей ливневой канализации"),
    ("13", "8", None, "требования к люкам и дождеприёмникам"),
    ("13", "9", None, "восстановление разрушенных крышек и люков в течение суток"),
    ("14", "12", None, "восстановление благоустройства после земляных работ"),
]

# вид нарушения → [(статья, часть, пункт)]; первый — основная норма
LINKS: dict[str, list[tuple[str, str, str | None]]] = {
    "yard_area_izh": [("12", "4", None), ("12", "5", None), ("3", "1", None)],
    "yard_area_mkd": [("12", "4", None), ("12", "5", None), ("5", "6", None), ("3", "1", None)],
    "outdoor_lighting_izh": [("6", "11", None), ("6", "10", None)],
    "outdoor_lighting_mkd": [("6", "11", None), ("6", "10", None), ("6", "9", None)],
    "facade_graffiti_mkd": [("4", "2.1", None), ("4", "2.3", None), ("8", "2", None)],
    "new_waste_site_mkd": [("5", "3", "3.1"), ("5", "3", "3.2"), ("5", "3", "3.6")],
    "missing_manholes_izh": [("13", "9", None), ("13", "8", None)],
    "missing_manholes_mkd": [("13", "9", None), ("13", "8", None), ("12", "4", None)],
    "snow_cleaning_izh": [("12", "4", None), ("12", "3", None)],
    "snow_cleaning_mkd": [("12", "4", None), ("12", "3", None), ("5", "3", "3.3")],
    "waste_collection_izh": [("5", "3", "3.4"), ("5", "3", "3.5")],
    "waste_collection_mkd": [("5", "3", "3.4"), ("5", "3", "3.7"), ("5", "3", "3.5")],
    "playgrounds_maintenance_mkd": [("9", "3", None), ("5", "5", "5.1")],
    "roads_maintenance_yards_mkd": [("12", "5", None), ("12", "2", None), ("3", "1", None)],
    "green_spaces_mkd": [("12", "5", None), ("7", "1", None), ("5", "5", "5.1")],
    "apartment_adjacent_area_mkd": [("12", "5", None), ("12", "4", None), ("5", "5", "5.1")],
    "waste_site_condition_izh": [("5", "3", "3.3"), ("12", "5", None)],
    "waste_site_condition_mkd": [("5", "3", "3.3"), ("5", "3", "3.6"), ("12", "5", None)],
    "icicles_mkd": [("12", "4", None), ("4", "2", None)],
    "roads_sidewalks_izh": [("12", "5", None), ("10", "1", None)],
    "road_sweeping_mkd": [("12", "5", None), ("12", "2", None)],
    "waste_site_surroundings_mkd": [("5", "3", "3.3"), ("5", "3", "3.7"), ("12", "5", None)],
}



def _reference(article: str, part: str | None, point: str | None) -> str:
    """Ссылка на норму так, как она печатается в документах.

    Название акта сюда не входит: оно печатается отдельно, из карточки акта.
    """

    if point:
        return f"пункт {point} части {part} статьи {article}"
    if part:
        return f"часть {part} статьи {article}"
    return f"статья {article}"


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Акт: берём существующий, иначе заводим.
    npa_id = connection.execute(
        sa.text("select id from npa where title = :title order by id limit 1"),
        {"title": ACT_TITLE},
    ).scalar()
    if npa_id is None:
        npa_id = connection.execute(
            sa.text(
                """
                INSERT INTO npa (kind, title, title_genitive, number, adopted_on,
                                 adopted_by, url, is_active)
                VALUES ('rules', :title, :genitive, '836',
                        CAST(:adopted_on AS date),
                        'Липецкий городской Совет депутатов',
                        'https://docs.cntd.ru/document/407523378', true)
                RETURNING id
                """
            ),
            {
                "title": ACT_TITLE,
                "genitive": ACT_GENITIVE,
                "adopted_on": ADOPTED_ON,
            },
        ).scalar_one()

    # 2. Нормы: добавляем только отсутствующие.
    articles: dict[tuple[str, str | None, str | None], int] = {}
    for number, title in ARTICLES:
        articles[(number, None, None)] = _ensure_article(
            connection, npa_id, number, None, None, title
        )

    for article, part, point, text in PARTS:
        articles[(article, part, point)] = _ensure_article(
            connection, npa_id, article, part, point, text
        )

    # 3. Связи «вид нарушения — норма».
    for code, norms in LINKS.items():
        for index, key in enumerate(norms):
            article_id = articles.get(key)
            if article_id is None:
                continue
            connection.execute(
                sa.text(
                    """
                    INSERT INTO violation_type_articles
                           (violation_type_id, npa_article_id, is_primary)
                    SELECT kind.id, :article_id, :is_primary
                      FROM violation_types AS kind
                     WHERE kind.code = :code
                    ON CONFLICT (violation_type_id, npa_article_id) DO NOTHING
                    """
                ),
                {
                    "article_id": article_id,
                    "is_primary": index == 0,
                    "code": code,
                },
            )


def _ensure_article(
    connection,
    npa_id: int,
    article: str,
    part: str | None,
    point: str | None,
    text: str,
) -> int:
    """Норма по тройке «статья, часть, пункт»: находит или заводит."""

    existing = connection.execute(
        sa.text(
            """
            select id from npa_articles
             where npa_id = :npa_id
               and coalesce(article_number, '') = coalesce(:article, '')
               and coalesce(part_number, '') = coalesce(:part, '')
               and coalesce(point_number, '') = coalesce(:point, '')
             order by id limit 1
            """
        ),
        {"npa_id": npa_id, "article": article, "part": part, "point": point},
    ).scalar()
    if existing is not None:
        return existing

    return connection.execute(
        sa.text(
            """
            INSERT INTO npa_articles
                   (npa_id, article_number, part_number, point_number,
                    text, reference_template, valid_from)
            VALUES (:npa_id, :article, :part, :point, :text, :reference,
                    CAST(:valid_from AS date))
            RETURNING id
            """
        ),
        {
            "npa_id": npa_id,
            "article": article,
            "part": part,
            "point": point,
            "text": text,
            "reference": _reference(article, part, point),
            "valid_from": VALID_FROM,
        },
    ).scalar_one()


def downgrade() -> None:
    # Наполнение справочника — не преобразование данных: откат удалил бы нормы,
    # на которые уже могут ссылаться нарушения. Оставляем справочник как есть.
    pass

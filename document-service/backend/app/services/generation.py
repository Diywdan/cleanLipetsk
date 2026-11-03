"""Формирование пакета документов по контрольному мероприятию.

Порядок работы:

1. собирается снимок данных по делу (snapshots.build_case_context);
2. состав пакета берётся из справочника (package_kind_documents), а не из
   кода — поэтому «при повторном предписании добавляется уведомление о
   явке» настраивается данными;
3. каждый документ заполняется по своей версии шаблона и сохраняется в
   файловое хранилище;
4. для каждого документа пишется свой снимок: перегенерация через год
   даст тот же результат, даже если справочники изменились.
"""

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt
from docxtpl import DocxTemplate, InlineImage
from jinja2 import Environment, StrictUndefined
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    ControlAction,
    ControlCase,
    Document,
    DocumentPackage,
    DocumentStatus,
    DocumentTemplate,
    DocumentType,
    PackageKind,
    PackageKindDocument,
)
from app.models.enums import FileKind, InspectionResult, PackageStatus, SnapshotEntityKind

from app.services import inspections as inspections_service
from app.services import pages as pages_service
from app.services import qr_placeholder, ru, snapshots, storage


# Документы, у которых считается число листов: именно их перечисляет
# в приложении направление. Считать у всех подряд — лишние секунды
# на сборку пакета без всякой пользы.
PAGE_COUNT_CODES = {"act", "prescription"}


# Общее окружение Jinja для всех шаблонов: строгие неопределённые значения
# и экранирование подставляемых данных.
STRICT_JINJA_ENV = Environment(undefined=StrictUndefined, autoescape=True)

# Документы, к которым из данных добавляется приложение с фотоматериалом.
PHOTO_APPENDIX_CODES = {"inspection_protocol"}

# Документы, в которых печатается QR-код из прокуратуры. Сам код система не
# создаёт: портал выдаёт готовую картинку, а мы ставим её на место, которое
# зарезервировано в бланке заготовкой «qr-placeholder». Размер места у бланков
# разный — в решении, предписании и акте 3.39 см, в протоколе осмотра 1.75 см,
# поэтому размер берётся из бланка, а не задаётся здесь.
QR_CODE_CODES = {"act", "prescription", "decision", "inspection_protocol"}
QR_CODE_SIZE_CM = 3.39


@dataclass
class GeneratedDocument:
    code: str
    document_id: int
    file_id: int
    snapshot_id: int
    number: str | None
    document_date: date | None


@dataclass
class GenerationResult:
    package_id: int
    created: list[GeneratedDocument] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    missing_templates: list[str] = field(default_factory=list)


def render(
    template_bytes: bytes, context: dict, images: dict[str, bytes] | None = None
) -> bytes:
    """Заполняет DOCX-шаблон, сохраняя оформление официального бланка.

    Строгий режим Jinja: если в контексте нет нужного значения, рендер
    падает с ошибкой. Иначе опечатка в шаблоне даёт пустое поле в готовом
    официальном документе, и заметить это можно только глазами.

    QR-код здесь не подставляется: в бланках на его месте стоит заготовка
    нужного размера, а сам код встаёт на её место после рендера
    (см. build_document_bytes). Если картинка всё же передана, оставляем
    прежний путь через InlineImage — им пользуются старые версии бланков,
    где ещё стоит тег {{ qr_code }}.
    """

    template = DocxTemplate(io.BytesIO(template_bytes))
    # В новых бланках на месте кода стоит заготовка фиксированного размера.
    # Код на её место ставится после рендера, поэтому объект картинки для
    # старого тега не нужен: docxtpl вписал бы её по своему размеру (3.39 см)
    # и сломал бы вёрстку протокола осмотра, где место меньше (1.75 см).
    if not qr_placeholder.has_placeholder(template_bytes):
        for name, data in (images or {}).items():
            context[name] = InlineImage(
                template,
                io.BytesIO(data),
                width=Cm(QR_CODE_SIZE_CM),
                height=Cm(QR_CODE_SIZE_CM),
            )
    template.render(context, jinja_env=STRICT_JINJA_ENV)
    buffer = io.BytesIO()
    template.save(buffer)
    return buffer.getvalue()


def _active_template(
    db: Session, document_type_id: int
) -> DocumentTemplate | None:
    stmt = (
        select(DocumentTemplate)
        .where(
            DocumentTemplate.document_type_id == document_type_id,
            DocumentTemplate.is_active.is_(True),
        )
        .order_by(DocumentTemplate.valid_from.desc().nullslast(), DocumentTemplate.id.desc())
    )
    return db.scalars(stmt).first()


def _local_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    converted = ru.to_display(value)
    return converted.date() if isinstance(converted, datetime) else converted


def _document_pages(db: Session, case_id: int, code: str) -> int | None:
    """Число листов последнего сформированного документа этого типа.

    Проставляется после подписания и подставляется в приложение к
    направлению. Если ещё не проставлено — в бланке остаётся место под запись.
    """

    stmt = (
        select(Document.pages)
        .join(DocumentPackage, Document.package_id == DocumentPackage.id)
        .join(DocumentType, Document.document_type_id == DocumentType.id)
        .where(
            DocumentPackage.control_case_id == case_id,
            DocumentType.code == code,
            Document.pages.is_not(None),
        )
        .order_by(Document.id.desc())
    )
    return db.scalars(stmt).first()


def _document_identity(
    case: ControlCase, code: str, inspection: ControlAction | None = None
) -> tuple[str | None, date | None]:
    """Номер и дата документа.

    Номера акта, решения и предписания присваивает портал прокуратуры,
    поэтому берём их из дела. Внутренние документы нумеруются отдельно —
    это следующий шаг.

    Дата протокола осмотра и акта — дата осмотра: документ составляется по
    его итогам, а не по плановому сроку заявки.
    """

    today = _local_date(datetime.now(timezone.utc))
    case_date = _local_date(case.actual_start_at or case.planned_start_at)
    if inspection is not None and inspection.started_at is not None:
        case_date = _local_date(inspection.started_at)

    if code == "act":
        # Номер мероприятия вводит пользователь, и он же идёт в акт. Если
        # акту присвоен отдельный номер, он и печатается.
        return case.act_number or case.erp_number, case_date or today
    if code == "assignment":
        return case.assignment_number, _local_date(case.assignment_date) or today
    if code == "inspection_protocol":
        return None, case_date or today
    if code == "prescription":
        prescription = case.prescriptions[0] if case.prescriptions else None
        issued_on = prescription.issued_on if prescription is not None else None
        # Номер предписания присваивает портал прокуратуры: это тот же номер
        # мероприятия, что и у акта. Если в карточке предписания номер не
        # заполнен, печатаем номер из заявки; если и его нет — пустую строку.
        if prescription is not None and prescription.number:
            return prescription.number, issued_on or today
        return case.erp_number, issued_on or today
    if code == "decision":
        decision = case.decisions[0] if case.decisions else None
        if decision is not None:
            return decision.number, decision.decision_date or today
        return None, today
    return None, _local_date(case.actual_end_at) or today


def _same_words(candidate: str, said: str) -> bool:
    """Сказано ли уже это (сравнение без регистра и лишних пробелов)."""

    def normalize(value: str) -> str:
        return " ".join(value.lower().replace(",", " ").split())

    return normalize(candidate) in normalize(said)


def append_photo_appendix(document_bytes: bytes, payload: dict) -> bytes:
    """Добавляет к документу приложение с фотоматериалом.

    Снимки лежат в файловом хранилище, а снимок данных хранит путь и sha256:
    поэтому приложение собирается из снимка и воспроизводится. python-docx
    читает PNG и JPEG сам, дополнительных библиотек не требуется.
    """

    photos = (payload.get("protocol") or {}).get("photos") or []
    if not photos:
        return document_bytes

    document = DocxDocument(io.BytesIO(document_bytes))

    # Ни разрыва, ни своего заголовка здесь нет: «Приложение к протоколу
    # осмотра…» уже печатает шаблон, вместе с адресом и датой выезда. Наша
    # задача — поставить снимки сразу под этим заголовком, на ту же страницу.
    # В конце шаблона остаются пустые абзацы и переносы строк — перед первым
    # снимком они дают десяток пустых строк. Убираем их до вставки фотографий.
    for paragraph in reversed(document.paragraphs):
        if paragraph.text.strip():
            for br in paragraph._element.findall(".//" + qn("w:br")):
                paragraph._element.remove(br)
            break
        paragraph._element.getparent().remove(paragraph._element)

    included = 0
    for photo in photos:
        stored = storage.absolute_path(photo["storage_path"])
        if not stored.exists():
            continue
        included += 1

        # Снимок держится со следующим снимком и не разрывается между
        # страницами: иначе он уезжает на следующую, оставляя заголовок одного.
        picture = document.add_paragraph()
        picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
        picture.paragraph_format.keep_with_next = True
        picture.paragraph_format.space_before = Pt(6)
        picture.paragraph_format.space_after = Pt(6)
        picture.add_run().add_picture(str(stored), width=Cm(15))

    if not included:
        return document_bytes

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def normalize_docx(data: bytes) -> bytes:
    """Перезаписывает пакет DOCX с фиксированными отметками времени.

    Содержимое при этом не меняется, но без нормализации два одинаковых по
    содержанию документа различаются байтами: ZIP хранит время упаковки.
    Из-за этого нельзя ни проверить воспроизводимость, ни сравнить файлы.
    """

    source = zipfile.ZipFile(io.BytesIO(data))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = item.external_attr
            target.writestr(info, source.read(item.filename))
    return buffer.getvalue()


def build_document_bytes(
    payload: dict, code: str, template_bytes: bytes
) -> bytes:
    """Полный проход сборки документа: шаблон плюс приложения из данных."""

    context = build_render_context(payload, code)
    document_bytes = render(template_bytes, context, _document_images(payload, code))
    if code in PHOTO_APPENDIX_CODES:
        document_bytes = append_photo_appendix(document_bytes, payload)
    # Место под QR-код зарезервировано в бланке заготовкой. Если код уже
    # загружен, ставим его на это место; если нет — заготовка и остаётся.
    qr_image = _document_images(payload, code).get("qr_code")
    if qr_image and qr_placeholder.has_placeholder(document_bytes):
        document_bytes = qr_placeholder.replace_placeholder(
            document_bytes, qr_image, name="qr.png"
        )
    # Если в бланке остался тег {{ qr_code }} (старые версии), он уже получил
    # картинку в render(); повторной вставки не нужно.
    return normalize_docx(document_bytes)


def _document_images(payload: dict, code: str) -> dict[str, bytes]:
    """Картинки, которые подставляются в документ.

    Пока это только QR-код из прокуратуры. Берём его из снимка данных: путь
    и хэш файла записаны в снимке, поэтому документ воспроизводится и после
    того, как код заменят новым.
    """

    if code not in QR_CODE_CODES:
        return {}
    qr = payload.get("qr_code") or {}
    storage_path = qr.get("storage_path")
    if not storage_path:
        return {}
    path = storage.absolute_path(storage_path)
    if not path.exists():
        return {}
    return {"qr_code": path.read_bytes()}


def build_render_context(payload: dict, code: str) -> dict:
    """Контекст шаблона целиком собирается из снимка данных.

    Поэтому перегенерация документа не зависит от текущего состояния
    справочников: номера, даты и город бланка уже лежат в снимке.
    """

    documents_meta = payload.get("documents", {})
    meta = documents_meta.get(code, {})
    context = dict(payload)
    context["documents"] = documents_meta
    # QR-код из прокуратуры: если картинки нет, значение пустое — в бланке
    # остаётся зарезервированное место. Ключ в снимке есть всегда, но может
    # быть пустым, поэтому проверяем значение, а не наличие ключа.
    if not context.get("qr_code"):
        context["qr_code"] = ""
    # Предписание ссылается на акт как на основание: «По результатам
    # проверки — АКТ от … № …».
    context["act"] = documents_meta.get("act")
    context["inspector"] = payload["inspectors"][0] if payload["inspectors"] else None
    if context["inspector"] is not None:
        # Должность в творительном падеже со строчной буквы: в протоколе об
        # административном правонарушении она идёт внутри предложения.
        # Считаем здесь, а не в снимке: снимки, сделанные раньше, этого поля
        # не содержат, и перегенерация старых документов не должна падать.
        instrumental = (
            context["inspector"].get("position_instrumental")
            or context["inspector"].get("position")
            or ""
        )
        context["inspector"]["position_instrumental_lower"] = (
            instrumental[:1].lower() + instrumental[1:]
        )

    # Дата документа разложена по частям: в бланках задания и акта день,
    # месяц и год стоят в отдельных ячейках таблицы.
    issued_on = meta.get("issued_on")
    issued_date = date.fromisoformat(issued_on) if issued_on else None
    context["document"] = {
        "code": code,
        "number": meta.get("number"),
        "issued_on": issued_on,
        "issued_on_short": meta.get("issued_on_short"),
        "issued_on_words": meta.get("issued_on_words"),
        "day": f"{issued_date.day:02d}" if issued_date else None,
        "month_words": (
            ru.date_words(issued_date, with_year=False).split()[-1]
            if issued_date
            else None
        ),
        "year": str(issued_date.year) if issued_date else None,
        "place": payload.get("meta", {}).get("document_place"),
        "today_short": ru.date_short(
            datetime.fromisoformat(payload["meta"]["built_at"])
        ),
    }
    return context


def _inspection_for_package(
    db: Session, case_id: int, package_kind_code: str
) -> ControlAction | None:
    """Осмотр, по которому собирается пакет документов.

    Первичный пакет описывает первичный осмотр, вторичный и пакет об
    исполнении — повторный: именно он показывает, устранено нарушение или нет.
    Если осмотра нужного вида ещё нет, берётся последний заведённый — так
    пакет собирается и по заявке, заведённой до появления осмотров.
    """

    if package_kind_code == "primary_prescription":
        return inspections_service.primary(db, case_id) or inspections_service.latest(
            db, case_id
        )
    return inspections_service.latest(db, case_id)


def available_packages(db: Session, case: ControlCase) -> list[dict]:
    """Какие пакеты можно собрать по состоянию заявки.

    Логика прозрачная и зависит только от осмотров:

    * есть первичный осмотр — можно собрать первичное предписание;
    * повторный осмотр показал, что нарушение устранено, — пакет об
      исполнении предписания;
    * повторный осмотр показал, что нарушение не устранено, — вторичное
      предписание.

    Пока осмотра нет, собирать нечего: сначала инспектор выходит на объект.
    Функция живёт в сервисе, потому что ею пользуются и страницы, и
    программный интерфейс.
    """

    primary = inspections_service.primary(db, case.id)
    repeat = inspections_service.repeat(db, case.id)

    available: list[dict] = []
    kinds = {kind.code: kind for kind in db.scalars(select(PackageKind))}

    # Первичное предписание собирают только до вторичного осмотра: после
    # него собирать первичный пакет уже поздно, иначе система предлагала бы
    # его и после повторного выхода на объект.
    if primary is not None and repeat is None and "primary_prescription" in kinds:
        available.append(
            {
                "kind": kinds["primary_prescription"],
                "title": "Создать первичный пакет документов",
                "hint": "по первичному осмотру",
            }
        )
    if repeat is not None and repeat.inspection_result is not None:
        if (
            repeat.inspection_result == InspectionResult.FIXED
            and "executed_prescription" in kinds
        ):
            available.append(
                {
                    "kind": kinds["executed_prescription"],
                    "title": "Создать исполненное предписание",
                    "hint": "нарушение устранено — задание, протокол осмотра, акт и письмо",
                }
            )
        if (
            repeat.inspection_result == InspectionResult.NOT_FIXED
            and "repeated_prescription" in kinds
        ):
            available.append(
                {
                    "kind": kinds["repeated_prescription"],
                    "title": "Создать вторичное предписание",
                    "hint": "нарушение не устранено — восемь документов, включая уведомление и протокол",
                }
            )
    return available


def generate_package(
    db: Session,
    case_id: int,
    package_kind_code: str = "primary_prescription",
    only_codes: list[str] | None = None,
    created_by_user_id: int | None = None,
    existing_package_id: int | None = None,
    commit: bool = True,
) -> GenerationResult:
    case = db.get(ControlCase, case_id)
    if case is None:
        raise ValueError(f"дело {case_id} не найдено")

    package_kind = db.scalar(
        select(PackageKind).where(PackageKind.code == package_kind_code)
    )
    if package_kind is None:
        raise ValueError(f"вид пакета {package_kind_code!r} не найден")

    package = None
    existing_codes: set[str] = set()
    if existing_package_id is not None:
        package = db.scalar(
            select(DocumentPackage)
            .where(
                DocumentPackage.id == existing_package_id,
                DocumentPackage.control_case_id == case.id,
                DocumentPackage.package_kind_id == package_kind.id,
            )
            .with_for_update()
        )
        if package is None:
            raise ValueError(
                f"пакет {existing_package_id} не принадлежит делу "
                f"{case_id} или имеет другой вид"
            )
        existing_codes = set(
            db.scalars(
                select(DocumentType.code)
                .join(Document, Document.document_type_id == DocumentType.id)
                .where(Document.package_id == package.id)
            )
        )

    # Документы собираются по осмотру: в первичном пакете — по первичному
    # осмотру, во вторичном и в пакете об исполнении — по повторному. Дата,
    # место и фотоматериал протокола осмотра берутся из него.
    inspection = _inspection_for_package(db, case_id, package_kind_code)
    payload = snapshots.build_case_context(db, case_id, inspection=inspection)

    composition = list(
        db.scalars(
            select(PackageKindDocument)
            .where(PackageKindDocument.package_kind_id == package_kind.id)
            .order_by(PackageKindDocument.sequence_no)
        )
    )

    # Номера и даты известны заранее для всего пакета: направление ссылается
    # на акт и предписание, которые могут формироваться позже него.
    documents_meta: dict[str, dict] = {}
    identities: dict[str, tuple[str | None, date | None]] = {}

    def add_document_meta(code: str, name: str) -> None:
        identity = _document_identity(case, code, inspection)
        identities[code] = identity
        number, document_date = identity
        pages = _document_pages(db, case.id, code)
        documents_meta[code] = {
            "code": code,
            "name": name,
            # «протокол осмотра от 22.09.2026» — в текстах акта и задания
            # наименование документа печатается со строчной буквы.
            "name_lower": (
                name[0].lower() + name[1:] if name else name
            ),
            # Номер присваивает портал прокуратуры, и его может ещё не быть:
            # тогда в бланке печатается пустое место, а не слово «None».
            # Пакет пересобирают, когда номер появится.
            "number": number or "",
            "issued_on": document_date.isoformat() if document_date else None,
            "issued_on_short": ru.date_short(document_date),
            "issued_on_words": ru.date_words(document_date),
            # Число листов печатается в приложении к направлению. Его
            # считает генератор по собранному документу; если посчитать
            # не удалось — печатается место для рукописной записи.
            "pages": pages,
            "pages_text": f" на {pages} л." if pages else " на ___ л.",
        }

    for item in composition:
        add_document_meta(item.document_type.code, item.document_type.name)

    # Бланки ссылаются и на документы прошлых пакетов: письмо о направлении
    # акта ссылается на предписание из первичного пакета, а в пакете об
    # исполнении предписания его нет. Поэтому к составу текущего пакета
    # добавляются последние документы дела по остальным видам.
    for document_type in db.scalars(
        select(DocumentType).order_by(DocumentType.sort_order, DocumentType.id)
    ):
        if document_type.code not in documents_meta:
            add_document_meta(document_type.code, document_type.name)

    # Номера и даты всего пакета входят в снимок: без этого документ нельзя
    # воспроизвести из снимка, не заглядывая в текущее состояние дела.
    payload["documents"] = documents_meta

    status = db.scalar(
        select(DocumentStatus).where(DocumentStatus.code == "generated")
    )

    if package is None:
        package = DocumentPackage(
            control_case_id=case.id,
            package_kind_id=package_kind.id,
            status=PackageStatus.GENERATING,
            created_by_user_id=created_by_user_id,
        )
        db.add(package)
        db.flush()
    else:
        package.status = PackageStatus.GENERATING

    package_snapshot = snapshots.save_snapshot(
        db,
        payload,
        entity_kind=SnapshotEntityKind.PACKAGE,
        entity_id=package.id,
        created_by_user_id=created_by_user_id,
        commit=False,
    )
    package.snapshot_id = package_snapshot.id

    result = GenerationResult(package_id=package.id)

    for item in composition:
        code = item.document_type.code
        if only_codes is not None and code not in only_codes:
            result.skipped.append(code)
            continue
        if code in existing_codes:
            result.skipped.append(code)
            continue

        template = _active_template(db, item.document_type_id)
        if template is None or template.file is None:
            result.missing_templates.append(code)
            continue

        number, document_date = identities[code]
        template_bytes = storage.read_bytes(template.file)
        document_bytes = build_document_bytes(payload, code, template_bytes)

        # Число листов нужно направлению: оно печатает, на скольких листах
        # акт и предписание. Считаем сразу после сборки документа и кладём
        # в данные пакета — направление собирается последним и берёт готовое.
        counted_pages = None
        if code in PAGE_COUNT_CODES:
            counted_pages = pages_service.count_pages(document_bytes)
            if counted_pages:
                documents_meta[code]["pages"] = counted_pages
                documents_meta[code]["pages_text"] = f" на {counted_pages} л."

        file = storage.save_bytes(
            db,
            document_bytes,
            f"{code}.docx",
            kind=FileKind.GENERATED,
            mime_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            commit=False,
        )
        document_snapshot = snapshots.save_snapshot(
            db,
            payload,
            entity_kind=SnapshotEntityKind.DOCUMENT,
            template_version=f"{template.code}-{template.version}",
            created_by_user_id=created_by_user_id,
            commit=False,
        )

        document = Document(
            package_id=package.id,
            document_type_id=item.document_type_id,
            template_id=template.id,
            number=number,
            document_date=document_date,
            status_id=status.id if status else None,
            erp_number=case.erp_number if item.document_type.uses_external_number else None,
            erp_code=case.erp_code if item.document_type.uses_external_number else None,
            snapshot_id=document_snapshot.id,
            generated_file_id=file.id,
            generated_at=datetime.now(timezone.utc),
            # Число листов: посчитано по собранному документу, а если
            # посчитать не удалось — остаётся прочерк в направлении.
            pages=counted_pages if counted_pages else _document_pages(db, case.id, code),
            created_by_user_id=created_by_user_id,
        )
        db.add(document)
        db.flush()

        result.created.append(
            GeneratedDocument(
                code=code,
                document_id=document.id,
                file_id=file.id,
                snapshot_id=document_snapshot.id,
                number=number,
                document_date=document_date,
            )
        )

    package.status = (
        PackageStatus.GENERATED if not result.missing_templates
        else PackageStatus.DRAFT
    )
    if commit:
        db.commit()
    return result

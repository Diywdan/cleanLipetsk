"""Названия значений справочников для интерфейса.

В базе значения хранятся кодами (`inspection`, `mu_material`) — так их
можно менять, не ломая данные. В интерфейсе коды показывать нельзя:
оператор должен видеть «осмотр» и «обращение», а не `photo_fixation`.
Названия собраны в одном месте, чтобы один и тот же код не назывался
по-разному в форме, карточке и документах.
"""

from app.models.enums import (
    CaseBaseKind,
    ContactKind,
    ControlActionType,
    InspectionResult,
    SignatoryBasisKind,
)


ACTION_TYPE_TITLES: dict[str, str] = {
    ControlActionType.INSPECTION.value: "осмотр",
    ControlActionType.INSTRUMENTAL_SURVEY.value: "инструментальное обследование",
    ControlActionType.SAMPLING.value: "отбор проб",
    ControlActionType.TESTING.value: "испытание",
    ControlActionType.EXPERTISE.value: "экспертиза",
    ControlActionType.PHOTO_FIXATION.value: "фотофиксация",
    ControlActionType.VIDEO_RECORDING.value: "видеозапись",
}

BASIS_KIND_TITLES: dict[str, str] = {
    CaseBaseKind.MU_MATERIAL.value: "материалы муниципального контроля",
    CaseBaseKind.APPEAL.value: "обращение",
    CaseBaseKind.PRESCRIPTION.value: "предписание",
    CaseBaseKind.PROSECUTOR_REQUEST.value: "требование прокуратуры",
    CaseBaseKind.PLAN.value: "план контрольных мероприятий",
    CaseBaseKind.OTHER.value: "иное основание",
}

SIGNATORY_BASIS_TITLES: dict[str, str] = {
    SignatoryBasisKind.CHARTER.value: "устав",
    SignatoryBasisKind.TRUST.value: "доверенность",
    SignatoryBasisKind.ORDER.value: "приказ",
    SignatoryBasisKind.OTHER.value: "иное",
}

CONTACT_KIND_TITLES: dict[str, str] = {
    ContactKind.EMAIL.value: "электронная почта",
    ContactKind.PHONE.value: "телефон",
}

INSPECTION_RESULT_TITLES: dict[str, str] = {
    InspectionResult.FIXED.value: "нарушение устранено",
    InspectionResult.NOT_FIXED.value: "нарушение не устранено",
}


def title(titles: dict[str, str], code: str | None) -> str | None:
    """Название значения или сам код, если названия нет.

    Неизвестный код показывается как есть: пустое место в форме хуже
    непереведённого слова — по нему хотя бы видно, что значение есть.
    """

    if code is None:
        return None
    return titles.get(code, code)


def options(
    values: list[str], titles: dict[str, str]
) -> list[tuple[str, str]]:
    """Пары «код, название» для списков формы."""

    return [(value, title(titles, value) or value) for value in values]

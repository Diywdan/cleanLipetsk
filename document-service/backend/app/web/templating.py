"""Общее окружение шаблонов.

Раньше каждый модуль создавал свой Jinja2Templates и регистрировал фильтры
только у себя — из-за этого страница пользователей падала с ошибкой
«нет фильтра dt». Теперь окружение одно на всё приложение.
"""

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.services import dictionary_admin, ru
from app.web import forms


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _display(value) -> str:
    """Дата и время для показа: «22.09.2026 08:30».

    Фильтр dt отдаёт формат поля ввода («2026-09-22T08:30») — он нужен
    в value= для datetime-local, иначе браузер значение не примет.
    Для показа нужен человеческий вид, поэтому фильтров два.
    """

    if value is None:
        return ""
    local = ru.to_display(value)
    if isinstance(local, datetime):
        return local.strftime("%d.%m.%Y %H:%M")
    return local.strftime("%d.%m.%Y")


# Даты и моменты времени в полях формы — в местном времени документов.
templates.env.filters["dt"] = forms.to_input

# Даты и моменты времени на странице — в том же времени, но для чтения.
templates.env.filters["dtr"] = _display

# Состояние значения справочника: в архиве или действует.
templates.env.globals["is_archived"] = dictionary_admin.is_archived


def _npa_groups(articles, genitive: bool = False) -> list[tuple[str, list]]:
    """Группирует нормы по акту, чтобы название печаталось один раз.

    В списке норм название акта повторялось после каждой строки: «часть 3
    статьи 12 Правил … — Правила …». Для одного акта достаточно назвать его
    один раз, а нормы перечислить через запятую.

    В строке квалификации название акта стоит после норм («часть 12 статьи 14
    Правил благоустройства…»), поэтому там нужен родительный падеж —
    genitive=True. В подписи группы формы годится именительный.
    """

    groups: list[tuple[str, list]] = []
    for article in articles or []:
        npa = getattr(article, "npa", None)
        if npa is None:
            title = ""
        elif genitive:
            title = getattr(npa, "title_genitive", None) or npa.title
        else:
            title = npa.title
        key = title or ""
        for group_title, items in groups:
            if group_title == key:
                items.append(article)
                break
        else:
            groups.append((key, [article]))
    return groups


def _join_norms(articles) -> str:
    """Строка для показа: «часть 3 статьи 12, часть 8 статьи 13 Правил …»."""

    parts: list[str] = []
    for title, items in _npa_groups(articles):
        references = ", ".join(
            article.reference_template for article in items
        )
        parts.append(f"{references} {title}".strip() if title else references)
    return "; ".join(parts)


templates.env.filters["npa_groups"] = _npa_groups
templates.env.filters["join_norms"] = _join_norms

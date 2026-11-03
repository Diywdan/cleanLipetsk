"""Разметка фотографии осмотра.

На снимок наносятся адрес объекта и дата осмотра: по документам осмотр
состоялся в определённое время, и подпись на фотографии должна этому
соответствовать. Текст рисуется с контрастным контуром, потому что белая
надпись читается не на каждом снимке, а чёрная теряется на тёмном.

Оригинал снимка при этом не меняется: размеченная копия хранится отдельным
файлом, и разметку всегда можно нанести заново — например, если дата осмотра
изменилась и документы переделывают.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services import ru


# Шрифты в образе: DejaVu из fonts-dejavu-core, Liberation из
# fonts-liberation. Оба кириллические — иначе надпись вышла бы квадратами.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

TEXT_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "black": (20, 20, 20),
    "yellow": (255, 221, 0),
    "red": (226, 32, 32),
}

OUTLINE_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (0, 0, 0),
    "black": (255, 255, 255),
    "yellow": (0, 0, 0),
    "red": (255, 255, 255),
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Разбивает строку по словам так, чтобы она влезла в ширину снимка."""

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def mark_photo(data: bytes, lines: list[str], color: str = "white") -> bytes:
    """Возвращает размеченный снимок: надписи внизу слева с контуром."""

    image = Image.open(BytesIO(data))
    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    # Размер шрифта зависит от снимка: на маленьком фото крупная надпись
    # закрыла бы сам объект съёмки.
    size = max(18, image.height // 28)
    font = _font(size)
    margin = max(12, image.height // 60)
    line_height = int(size * 1.35)
    stroke = max(2, size // 9)

    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap(draw, line, font, image.width - 2 * margin))

    y = image.height - margin - line_height * len(wrapped)
    for line in wrapped:
        draw.text(
            (margin, y),
            line,
            font=font,
            fill=TEXT_COLORS.get(color, TEXT_COLORS["white"]),
            stroke_width=stroke,
            stroke_fill=OUTLINE_COLORS.get(color, OUTLINE_COLORS["white"]),
        )
        y += line_height

    out = BytesIO()
    image.save(out, format="JPEG", quality=92)
    return out.getvalue()


def annotation_text(action, address: str | None) -> list[str]:
    """Надписи для снимка: адрес объекта и дата со временем осмотра."""

    lines: list[str] = []
    if address:
        lines.append(address)
    if action.started_at is not None:
        lines.append(
            f"{ru.date_short(action.started_at)} {ru.time_short(action.started_at)}"
        )
    return lines

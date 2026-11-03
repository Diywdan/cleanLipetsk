"""Файловое хранилище: метаданные и хэши, содержимое — на диске."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin, code_enum
from app.models.enums import FileKind


if TYPE_CHECKING:
    from app.models.user import User


class StoredFile(IntIdMixin, TimestampMixin, Base):
    """Любой файл системы: шаблон, сгенерированный документ, скан, фото.

    Содержимое в БД не пишется — только путь в томе и sha256, по которому
    можно доказать, что файл не подменяли.
    """

    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_sha256", "sha256"),
    )

    kind: Mapped[FileKind] = mapped_column(
        code_enum(FileKind, "file_kind"),
        nullable=False,
        server_default=FileKind.ATTACHMENT.value,
    )

    storage_path: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))

    # Для фотоматериалов: дата и время съёмки — из EXIF либо введены вручную.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Подпись, которая печатается под снимком в приложении к протоколу
    # осмотра: «Общий вид контейнерной площадки».
    caption: Mapped[str | None] = mapped_column(String(500))
    # Место съёмки: может не совпадать с местом проведения действия.
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))

    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    uploaded_by: Mapped["User | None"] = relationship()
    address: Mapped["Address | None"] = relationship()  # noqa: F821

"""Число листов документа.

Официальные бланки печатают число листов в приложении к направлению
(«на 3 л. в 1 экз.»). Считать вручную неудобно и легко ошибиться, поэтому
документ конвертируется в PDF, а страницы считаются по файлу: разбивка на
страницы зависит от шрифтов и полей, и «на глаз» её не определить.

Конвертацию делает LibreOffice в режиме командной строки — тот же движок,
которым документ печатался бы. В образе стоят метрически совместимые шрифты
(Liberation вместо Times New Roman и Arial): без них подстановка шрифта
изменила бы разбивку на страницы, и число листов разошлось бы с тем,
что видит оператор в Word.

Если конвертера нет, подсчёт не выполняется: вернуть неверное число хуже,
чем оставить в документе место для рукописной записи.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path


SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
PDFINFO = shutil.which("pdfinfo")

# Конвертация большого документа может занять время, но не бесконечно.
CONVERT_TIMEOUT = 120
INFO_TIMEOUT = 30


def available() -> bool:
    """Можно ли считать листы: нужны и конвертер, и средство чтения PDF."""

    return bool(SOFFICE and PDFINFO)


def _pdf_pages(pdf: Path) -> int | None:
    """Число страниц в готовом PDF."""

    if not pdf.exists():
        return None
    try:
        info = subprocess.run(
            [str(PDFINFO), str(pdf)],
            capture_output=True,
            text=True,
            timeout=INFO_TIMEOUT,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    for line in info.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def count_pages(document_bytes: bytes) -> int | None:
    """Число листов документа или None, если посчитать не удалось."""

    if not available():
        return None

    with tempfile.TemporaryDirectory() as work:
        work_dir = Path(work)
        source = work_dir / "document.docx"
        source.write_bytes(document_bytes)

        # Отдельный профиль на каждый запуск: иначе одновременные сборки
        # дерутся за один каталог настроек LibreOffice.
        profile = work_dir / "profile"
        command = [
            str(SOFFICE),
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work_dir),
            str(source),
        ]
        try:
            subprocess.run(
                command,
                capture_output=True,
                timeout=CONVERT_TIMEOUT,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None

        return _pdf_pages(work_dir / "document.pdf")

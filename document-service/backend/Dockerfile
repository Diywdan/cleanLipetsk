FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# LibreOffice нужен для подсчёта числа листов: документ конвертируется в PDF
# и страницы считаются по файлу. Шрифты Liberation метрически совместимы
# с Times New Roman и Arial — без них подстановка шрифта изменила бы разбивку
# на страницы, и число листов разошлось бы с Word.
# poppler-utils даёт pdfinfo, которым страницы и считаются.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-liberation \
        fonts-dejavu-core \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Где pypi.org недоступен (сеть ЦОД), индекс подменяется при сборке:
#   docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --retries 10 --timeout 30 -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

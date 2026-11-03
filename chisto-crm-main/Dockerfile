FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# В сети ЦОД pypi.org режется по имени хоста — при сборке на сервере передать зеркало:
#   docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app
COPY pyproject.toml ./
# Зависимости — из pyproject.toml, код запускается из /app: так в образ попадают
# миграции и справочник app/data/categories.json без настройки package-data.
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install --index-url "$PIP_INDEX_URL" --retries 10 --timeout 30 -r /tmp/requirements.txt \
 && useradd --system --uid 10001 --home-dir /app crm \
 && mkdir -p /app/data/files && chown -R crm /app/data

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

USER crm
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Playwright chromium + deps (used by the enrich crawler)
RUN playwright install --with-deps chromium

COPY . .

RUN mkdir -p /app/secrets

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/carnaticidx/app \
    FLASK_APP=app:app \
    FLASK_ENV=production

WORKDIR /carnaticidx

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt /carnaticidx/app/requirements.txt
RUN pip install --no-cache-dir -r /carnaticidx/app/requirements.txt

COPY app /carnaticidx/app
COPY client /carnaticidx/client
COPY ingest /carnaticidx/ingest

WORKDIR /carnaticidx/app

EXPOSE 8000

COPY app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

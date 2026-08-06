FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY quantmind /app/quantmind
COPY examples /app/examples

RUN pip install --no-cache-dir -e '.[api]'

ENV PYTHONUNBUFFERED=1
ENV QUANTMIND_AUDIT_DB_PATH=/data/audit.db

EXPOSE 8000

CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "quantmind.api:app", "-b", "0.0.0.0:8000"]

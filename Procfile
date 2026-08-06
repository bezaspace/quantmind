web: gunicorn -w 1 -k uvicorn.workers.UvicornWorker quantmind.api:app -b 0.0.0.0:${PORT:-8000}

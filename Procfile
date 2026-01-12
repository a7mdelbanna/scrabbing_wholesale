# Railway/Render Procfile
# Main API server
web: uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}

# Background worker (create separate service with this command)
# worker: celery -A src.workers.celery_app worker --loglevel=info --concurrency=2

# Scheduler (create separate service with this command)
# scheduler: python -m src.scheduler.run

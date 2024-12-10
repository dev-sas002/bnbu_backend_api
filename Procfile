release: python manage.py migrate && mkdir -p documents
web: gunicorn bnbu_backend_api.wsgi --log-file -
worker: mkdir -p documents && celery -A bnbu_backend_api worker --pool=threads --loglevel=info -E --concurrency=${CELERY_CONCURRENCY:-2}

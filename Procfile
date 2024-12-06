release: python manage.py migrate
web: gunicorn bnbu_backend_api.wsgi --log-file --timeout 300
worker: celery -A bnbu_backend_api worker --pool=threads --loglevel=info -E --concurrency=${CELERY_CONCURRENCY:-2}

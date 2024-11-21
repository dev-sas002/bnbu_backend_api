web: gunicorn bnbu_backend_api.wsgi --log-file -
worker: celery -A bnbu_backend_api worker --loglevel=info -E


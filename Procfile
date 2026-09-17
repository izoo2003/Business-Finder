web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A config worker -l info
beat: celery -A config beat -l info
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py seed_sources

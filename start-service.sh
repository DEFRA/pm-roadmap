#!/bin/sh
set -eu

if [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "DJANGO_SUPERUSER_PASSWORD is set; ensuring admin user exists"
  export DJANGO_SUPERUSER_USERNAME=admin
  export DJANGO_SUPERUSER_EMAIL=admin@example.com
  python manage.py createsuperuser --noinput || true
else
  echo "DJANGO_SUPERUSER_PASSWORD is not set; skipping admin user creation"
fi

python manage.py runserver 8085

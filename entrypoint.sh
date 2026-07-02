#!/bin/bash
litestream restore  -if-replica-exists -config litestream.yml $PWD/data/db.sqlite3 || true
python manage.py migrate
exec litestream replicate --config ./litestream.yml -exec ./start-service.sh

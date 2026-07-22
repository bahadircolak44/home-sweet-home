#!/bin/sh
set -eu

python - <<'PY'
import os
import time

import psycopg

database_url = os.environ["DATABASE_URL"]
for attempt in range(30):
    try:
        with psycopg.connect(database_url):
            print("PostgreSQL is available.")
            break
    except psycopg.OperationalError:
        if attempt == 29:
            raise
        print("Waiting for PostgreSQL...")
        time.sleep(1)
PY

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"

# Home Sweet Home

Home Sweet Home is a private household web application. Its first module provides shared grocery lists: household members can maintain multiple lists, add and purchase items together, and review completed trips in history.

Public registration is intentionally excluded from this MVP. Users and household memberships are initially managed through Django Admin.

## Technology stack

- Django with server-rendered templates
- HTMX for item add, toggle, and delete interactions
- PostgreSQL with Psycopg 3
- Docker and Docker Compose
- WhiteNoise for static files
- Plain, mobile-first CSS

## Prerequisites

- Docker
- Docker Compose
- Git
- Optional: Python 3.13 for management commands outside Docker

## Environment configuration

Create a local environment file from the safe example:

```bash
cp .env.example .env
```

`DJANGO_SETTINGS_MODULE` selects local or production settings. `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` configure Django. `DATABASE_URL` is the source of truth for Django's PostgreSQL connection. The `POSTGRES_*` variables initialize the Compose database service. `POSTGRES_HOST_PORT` and `WEB_PORT` may be changed if ports `5432` or `8000` are already in use.

The checked-in VS Code launch configurations use `localhost` for PostgreSQL automatically. The Docker environment uses `db`.

## Start the application with Docker

```bash
docker compose up --build
```

The entrypoint waits for PostgreSQL, applies migrations, and collects static files. Open the application at:

```text
http://127.0.0.1:8000/
```

## First migrations

After changing models, create and apply migrations with:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

`makemigrations` creates migration files from model changes. `migrate` applies migration files to PostgreSQL.

After cloning a repository that already contains migration files, the normal command is simply:

```bash
docker compose exec web python manage.py migrate
```

## Create a superuser

```bash
docker compose exec web python manage.py createsuperuser
```

Django Admin is available at:

```text
http://127.0.0.1:8000/admin/
```

## Initial household setup

1. Create a superuser.
2. Start the application.
3. Open Django Admin.
4. Create the second user under Users.
5. Create one household, for example `Home`.
6. Create two household memberships:
   - Superuser → Home
   - Second user → Home
7. Log into the main application using either account.

Both users must belong to the same household to see the same grocery lists.

## VS Code runners

Open **Run and Debug** in VS Code and select one of the included configurations:

- `Django: Run Server`
- `Django: Make Migrations`
- `Django: Migrate`
- `Django: Create Superuser`
- `Django: Run Tests`
- `Django: Management Command` for an arbitrary command such as `check` or `shell`

Start the PostgreSQL service first with `docker compose up -d db`. These runners use the existing `.venv` and connect to the mapped database port at `localhost:5432`.

## Useful Docker commands

```bash
docker compose up --build
```

Build images and run the database and web application in the foreground.

```bash
docker compose up -d
```

Run the services in the background.

```bash
docker compose down
```

Stop and remove containers while preserving database data.

```bash
docker compose down -v
```

Stop the services and delete named volumes. **This deletes the local PostgreSQL volume and removes all local database data.**

```bash
docker compose logs -f web
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py shell
```

These commands respectively follow web logs, validate Django configuration, create and apply migrations, create an admin user, run tests, collect static assets, and open the Django shell.

## Running management commands outside Docker

Activate the existing virtual environment and install dependencies:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python manage.py check
```

PostgreSQL must still be reachable. Inside Docker the database host is `db`; from the host machine it is usually `localhost`. The VS Code runners override `DATABASE_URL` with the correct host value.

## Future production database

Production can use any standard PostgreSQL provider by replacing `DATABASE_URL` and selecting production settings:

```dotenv
DJANGO_SETTINGS_MODULE=home_sweet_home.settings.production
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

Set a secure `SECRET_KEY`, strict `ALLOWED_HOSTS`, and strict `CSRF_TRUSTED_ORIGINS` for the deployment. HTTPS redirect behavior can be changed with `SECURE_SSL_REDIRECT`.

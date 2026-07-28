# Home Sweet Home

Home Sweet Home is a private household web application with a central dashboard for household modules. Household members can maintain shared grocery lists, add quantities and optional product details, purchase items together, and review completed trips in history. They can also create shared chore sessions, assign tasks, complete them together, and review completed sessions in history. Talk Later stores shared topics to discuss, with an optional reminder at the right time.

Public registration is intentionally excluded from this MVP. Users and household memberships are initially managed through Django Admin.

## Technology stack

- Django with server-rendered templates
- HTMX for item add, toggle, and delete interactions
- PostgreSQL with Psycopg 3
- Docker and Docker Compose
- WhiteNoise for static files
- Plain, mobile-first CSS
- Progressive Web App manifest and conservative static-asset service worker

## Application modules

The authenticated root route displays the Home Sweet Home dashboard. Grocery Lists is available under `/groceries/`, Household Chores is available under `/chores/`, and Talk Later is available under `/talk-later/`.

Grocery items support a required quantity and an optional description. Descriptions may contain notes, brand preferences, or product links. Valid URLs are converted to safe external links while user-entered HTML remains escaped. Active items can be edited; completed lists remain read-only.

Household Chores uses focused, shared sessions such as `This Week` or `Weekend Cleaning`. Household members can add custom tasks with a quantity, assign them to current household members, mark them done or not done, and view incomplete tasks grouped by assignee. Completed tasks move to a shared list at the bottom of the active session, where their assignee and completer are visible. The Quick List stores reusable chores with an optional default assignee; each reusable chore can be added once to a session. Completed sessions and their tasks are read-only in Chore History.

Talk Later is intentionally small: add a topic, optionally choose a local date and time, and mark it done after discussing it. Scheduled topics send one Web Push reminder to every subscribed device for current household members, including the person who created it. Marking a topic done prevents a future reminder; reopening an already processed reminder does not send it again unless the topic is explicitly rescheduled. Notes stay in the app and are never included in the notification.

## Progressive Web App support

Home Sweet Home includes a web manifest, original application icons, and a minimal service worker. The service worker caches only local CSS, JavaScript, the manifest, and application icons. Authenticated pages, forms, and HTMX mutation responses are never cached, and full offline grocery-list functionality is not implemented.

## Web Push notifications

Home Sweet Home uses standards-based Web Push to notify other members of a household when a grocery list, grocery item, or chore task changes. Notifications are delivered directly from the Django application to each browser's Push subscription; no Firebase, queue, or separate notification service is used. The person making a change is never notified about their own change. Notification text contains list, item, session, and task names only: item descriptions and product URLs are never sent to the lock screen.

Permission and subscriptions are per device and per browser. Every household member must enable notifications separately on each installed device or browser. Signing out does not necessarily revoke operating-system notification permission, so use **Disable Notifications** before removing a personal device from someone else's account.

To avoid notification noise, each receiving device tracks household grocery activity. The first grocery change sends a notification; later changes reset a ten-minute quiet period without sending more notifications. The first new change after ten minutes of inactivity sends a new notification.

Talk Later scheduled reminders do not use that grocery activity cooldown. They are processed once for a schedule, including when a household has no active subscriptions. Notification permission remains per browser and device, so every device that should receive a reminder must enable notifications separately.

### Generate local VAPID keys

Web Push uses one VAPID key pair per environment. Generate a local pair from the repository root on the host, after activating `.venv` and installing the requirements. Do not run this command through `docker compose exec`: the development container uses an unprivileged user that cannot write to the bind-mounted project directory.

```bash
vapid --gen
vapid --applicationServerKey --private-key private_key.pem
```

The first command creates `private_key.pem` and `public_key.pem`. Copy the displayed Application Server Key from the second command into `VAPID_PUBLIC_KEY`. The private key files are ignored by Git and Docker, and must never be committed or shared in logs. Keep the same VAPID key pair after users subscribe: regenerating it invalidates existing browser subscriptions.

Add the following to `.env` for local development:

```dotenv
PUSH_NOTIFICATIONS_ENABLED=True
VAPID_PUBLIC_KEY=your-application-server-key
VAPID_PRIVATE_KEY_PATH=private_key.pem
VAPID_SUBJECT=mailto:notifications@example.com
TALK_LATER_REMINDER_JOB_TOKEN=replace-with-a-long-random-secret
```

`VAPID_PRIVATE_KEY_PATH` may be relative to the repository root locally or an absolute path in production. When `PUSH_NOTIFICATIONS_ENABLED=True`, the application fails at startup if any VAPID setting is missing or the private-key path does not point to a file.

### Test Talk Later reminders locally

1. Start Docker and enable notifications in each test browser or device.
2. Create a Talk Later topic one or two minutes ahead.
3. Run the processor:

```bash
docker compose exec web python manage.py process_talk_later_reminders
```

4. Verify the notification opens the topic when selected.
5. Run the command again and verify that no duplicate reminder is sent.

The command accepts `--limit` for a smaller batch. The scheduler endpoint can also be called locally with the token from `.env`:

```bash
curl -X POST -H "X-Reminder-Token: replace-with-local-token" http://127.0.0.1:8000/internal/talk-later/process-reminders/
```

### Run Talk Later reminders with Cloud Scheduler

Exact-time reminders need server-side polling. The application does not add a queue or background worker, so the service owner must configure Cloud Scheduler after deploying a revision with push enabled.

1. Generate a token with `openssl rand -hex 32`.
2. Store it as the Cloud Run environment variable `TALK_LATER_REMINDER_JOB_TOKEN`.
3. Deploy a new revision.
4. Create a Google Cloud Scheduler HTTP job with:
   - Schedule: `* * * * *`
   - Time zone: `Europe/Amsterdam`
   - Method: `POST`
   - URL: `https://<cloud-run-url>/internal/talk-later/process-reminders/`
   - Header: `X-Reminder-Token: <same-secret>`
5. Use **Run now** and verify HTTP 200.
6. Schedule a test topic a few minutes ahead.
7. Verify all subscribed household devices receive one reminder.

For example, adapt the following placeholders to the deployed service:

```bash
gcloud scheduler jobs create http talk-later-reminders \
  --schedule="* * * * *" \
  --time-zone="Europe/Amsterdam" \
  --uri="https://<cloud-run-url>/internal/talk-later/process-reminders/" \
  --http-method=POST \
  --headers="X-Reminder-Token=<same-secret>"
```

Disabling Scheduler stops timed reminders. A missing subscription or denied device permission means that device cannot receive a reminder. The scheduler token is separate from the VAPID private key. If VAPID keys change, devices must subscribe again.

### Talk Later troubleshooting

- If push is disabled, reminder processing safely does nothing until `PUSH_NOTIFICATIONS_ENABLED=True` and the VAPID configuration is valid.
- If no subscriptions are active, a due topic is recorded as processed without a delivery; enable notifications on the intended device before scheduling another test.
- If a device denied permission, re-enable it in the browser or operating-system notification settings and subscribe again from the dashboard.
- If scheduled reminders never arrive, verify that Cloud Scheduler is enabled, its time zone is `Europe/Amsterdam`, and the job is returning HTTP 200.
- HTTP 403 from the internal endpoint means its `X-Reminder-Token` does not exactly match `TALK_LATER_REMINDER_JOB_TOKEN`.
- If the VAPID keys changed, existing devices must subscribe again.

### Enable, test, and disable on a device

1. Sign in and open the dashboard.
2. On Android, install the app from Chrome if desired, then select **Enable Notifications** and accept the browser permission prompt.
3. On iPhone or iPad, open the site in Safari, use Share → **Add to Home Screen**, launch the installed app, then select **Enable Notifications**. iOS web push is available only from the installed Home Screen app.
4. Select **Send Test Notification** to verify the current device only.
5. Select **Disable Notifications** before handing a device to someone else; this removes the server record and unsubscribes the browser.

If permission was denied, enable notifications again from the browser or device settings, then return to the dashboard. The application never asks for permission automatically on page load.

### Cloud Run and Secret Manager

Store the VAPID private key in Secret Manager, alongside the existing database URL and Django secret. Mount the secret as a read-only file in the Cloud Run service and configure `VAPID_PRIVATE_KEY_PATH` with that absolute mounted path. Configure `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`, and `PUSH_NOTIFICATIONS_ENABLED=True` as non-secret runtime environment variables. Grant the runtime service account access only to the required secret versions. Do not place the private key in a repository, image, GitHub variable, or build log.

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

## Install on a phone

### Android

Open the application in Chrome and choose Install App or Add to Home screen.

### iPhone and iPad

Open the application in Safari, open the Share menu, and select Add to Home Screen.

Installation features require HTTPS in production. Supported browsers accept `localhost` for local development, so the Docker workflow may continue to use HTTP. Production should be deployed behind HTTPS.

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

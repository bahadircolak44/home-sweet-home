# Home Sweet Home

Home Sweet Home is a private household web application with a central dashboard for household modules. Each household starts with permanent Albert and Türk Market grocery lists and can create additional shared lists as needed. Members can add quantities and optional product details, purchase items together, and review purchases in history after one week. They can also create shared chore sessions, assign tasks, complete them together, and review completed sessions in history. Talk Later stores shared topics to discuss, with an optional reminder at the right time.

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

Grocery items support a required quantity and an optional description. Descriptions may contain notes, brand preferences, or product links. Valid URLs are converted to safe external links while user-entered HTML remains escaped. Albert and Türk Market are fixed starter lists; additional lists can be created, edited, completed, and deleted. All active lists retain purchased items for seven days, then show them as read-only purchase history.

Household Chores uses focused, shared sessions such as `This Week` or `Weekend Cleaning`. Household members can add custom tasks, optionally set a due date, assign them to current household members, mark them done or not done, and view incomplete tasks grouped by assignee. Completed tasks with the same title are combined into a shared count at the bottom of the active session, together with the household members who completed them. The Quick List stores reusable chores with an optional default assignee and can be used repeatedly. Completed sessions and their tasks are read-only in Chore History.

Talk Later is intentionally small: add a topic, optionally choose a local date and time, and mark it done after discussing it. Scheduled topics send one Web Push reminder to every subscribed device for current household members, including the person who created it. Marking a topic done prevents a future reminder; reopening an already processed reminder does not send it again unless the topic is explicitly rescheduled. Notes stay in the app and are never included in the notification.

## Quick Add with AI

**Quick Add with AI** appears near the top of the authenticated dashboard only when `AI_ASSISTANT_ENABLED=True` and the user belongs to a household. It accepts a short typed command or a push-to-talk recording in Turkish or English, such as `Add milk to Albert` or `Albert listesine iki elma ekle`.

The first version can propose only one of these additions:

- One grocery item to an active Grocery List.
- One chore task to an active Chore Session, optionally assigned to a current household member.
- One Talk Later topic, optionally with a future scheduled date and time.

Nothing is added while the command is interpreted. The user must review the transcript and deterministic summary, then select **Confirm and Add** in a separate POST. The assistant cannot delete, edit, complete, toggle, purchase, reschedule, or perform multiple operations. It uses normal authenticated HTTP requests: WebSockets and the Realtime API are deliberately not used in this MVP.

The browser requests microphone permission only after the recording button is selected. It stops the clip after `AI_AUDIO_MAX_SECONDS`; the server-enforced limit is `AI_AUDIO_MAX_BYTES`. Production microphone access requires HTTPS; supported browsers treat `localhost` as secure for local development. Typing always remains available if recording is unsupported or permission is denied.

### OpenAI setup and privacy

Create an OpenAI API project, add billing, and create a server-side API key. API usage is billed separately from a ChatGPT subscription. Keep the key out of browser code, Git, logs, database rows, and Django Admin.

Add these values to local `.env` after copying `.env.example`:

```dotenv
AI_ASSISTANT_ENABLED=True
OPENAI_API_KEY=your-server-side-openai-api-key
OPENAI_COMMAND_MODEL=gpt-5-mini
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
AI_COMMAND_TIMEOUT_SECONDS=20
AI_COMMAND_PROPOSAL_TTL_SECONDS=600
AI_AUDIO_MAX_SECONDS=20
AI_AUDIO_MAX_BYTES=5242880
AI_COMMANDS_PER_MINUTE=10
```

The application fails startup with a clear configuration error if the feature is enabled without an API key or either model name. Interpretation uses the Responses API with four strict function schemas and a minimal authorized context: current time/timezone, active list and session IDs/names, and current household member IDs/display names. Uploaded audio is sent directly for transcription and is never stored. Raw OpenAI responses, keys, access tokens, emails, completed history, and audio bytes are never stored. Proposals are short-lived (ten minutes by default), confirmed under a database lock, and rate-limited to ten interpretations per user per minute by default.

For manual privacy maintenance, remove old terminal records with:

```bash
docker compose exec web python manage.py purge_ai_assistant_commands --older-than-days 30
```

### Cloud Run Secret Manager setup

Before deploying the included production workflow, create the `home-sweet-home-openai-api-key` Secret Manager secret, add the API key as its version, and grant the Cloud Run runtime service account access to that secret. The workflow maps it only to the `OPENAI_API_KEY` runtime environment variable; it must not be a GitHub variable, repository file, or build argument. The workflow enables the feature with the model and safety limits shown above. Set `AI_ASSISTANT_ENABLED=False` in the deployment configuration if the secret has not been created yet.

### Quick Add troubleshooting

- **Panel is missing:** Ensure `AI_ASSISTANT_ENABLED=True`, restart the app, and confirm the signed-in user has a household membership.
- **Missing or invalid API key / insufficient credits / model unavailable:** Check the server-side key, billing/project status, model names, and Secret Manager access. Nothing is added on an API error.
- **Microphone denied or unsupported:** Re-enable permission in the browser or device settings, use HTTPS in production, or type the command instead.
- **Audio too large:** Record a shorter clip; file size is the server-enforced boundary.
- **Command is ambiguous or target is missing:** Include the exact active Grocery List, Chore Session, or household member name.
- **Proposal expired:** Submit the command again and explicitly confirm the new preview.
- **Timeout or rate limit:** Wait briefly and retry. The assistant keeps Grocery Lists, Chores, Talk Later, push, and Calendar functionality independent of OpenAI availability.

## Google Sign-In and Google Calendar

Google Sign-In links an approved Google account to an existing Django user; it never creates a new Home Sweet Home user. Existing user IDs, usernames, password hashes, permissions, staff/superuser state, household memberships, and application data remain in place. This feature is disabled by default. Password sign-in remains available as a fallback until every user has linked and tested Google sign-in.

The first Google authorization requests only `openid`, `email`, `profile`, and Google Calendar event ownership access. The server uses the OAuth 2.0 authorization-code flow with a session state value, backend ID-token verification, offline access, and encrypted refresh-token storage. No OAuth token is sent to browser storage. Only accounts in `GOOGLE_ALLOWED_EMAILS` can proceed, and the Google email must be verified.

### Existing-user linking

The integration resolves a verified, allowlisted Google identity in this order:

1. An existing matching Google subject.
2. An existing matching normalized Google email when its subject is not conflicting.
3. The explicit `GOOGLE_LEGACY_USER_MAP` email-to-username mapping.
4. Exactly one existing Django user with a case-insensitive matching email address.

An unknown or ambiguous account is rejected with no automatic registration. Use the explicit legacy map for the two current household users even if their local Django email fields happen to match today; it makes rollout deterministic.

### Local configuration

Add the following to local `.env` only after creating a Google Web OAuth client. Keep the feature disabled until every required value is present.

```dotenv
GOOGLE_OAUTH_ENABLED=False
GOOGLE_CALENDAR_ENABLED=False

GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/accounts/google/callback/

GOOGLE_ALLOWED_EMAILS=first.person@gmail.com,second.person@gmail.com
GOOGLE_LEGACY_USER_MAP=first.person@gmail.com:existing_username,second.person@gmail.com:other_username
GOOGLE_TOKEN_ENCRYPTION_KEY=

GOOGLE_CALENDAR_EVENT_DURATION_MINUTES=30
PASSWORD_LOGIN_ENABLED=True
```

Generate the token-encryption key once and store it safely:

```bash
docker compose run --rm -T web python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`GOOGLE_TOKEN_ENCRYPTION_KEY` must be a valid Fernet key. The application intentionally fails startup when OAuth is enabled and the key is missing or invalid. Never generate a replacement key during application startup, commit it, or write it to logs. Changing or losing it means every user must reconnect because previously stored refresh tokens cannot be decrypted.

When OAuth is enabled, Django also requires the client ID, client secret, redirect URI, a non-empty allowlist, and a valid Fernet key. Calendar integration additionally requires OAuth. The legacy map rejects malformed entries, duplicate emails, and duplicate usernames at startup.

### Google Cloud setup

1. Create or select the Google Cloud project for this application.
2. Enable **Google Calendar API**.
3. Configure Google Auth Platform branding, audience, contact details, and only the required scopes listed above.
4. While the app is in Testing, add the two approved Google accounts as test users. Testing authorizations can expire, so reconnect may be required.
5. Create a **Web application** OAuth client.
6. Add exact authorized redirect URIs. For example:

   ```text
   http://localhost:8000/accounts/google/callback/
   https://your-domain.example/accounts/google/callback/
   ```

   Google requires an exact match, including scheme, host, path, and trailing slash.
7. Store the OAuth client secret and Fernet key in Secret Manager. Do not put them in GitHub variables, the repository, browser code, or build logs.
8. Configure the production values as Cloud Run environment variables or Secret Manager references. Use an HTTPS production callback URL.

The included continuous-deployment workflow expects the Google configuration to exist as Secret Manager secrets named `home-sweet-home-google-oauth-client-id`, `home-sweet-home-google-oauth-client-secret`, `home-sweet-home-google-oauth-redirect-uri`, `home-sweet-home-google-allowed-emails`, `home-sweet-home-google-legacy-user-map`, and `home-sweet-home-google-token-encryption-key`. Grant the function runtime service account access to every one of them before deployment.

Do not use Firebase Authentication, service accounts, Workspace domain-wide delegation, or another Google API for this feature. Move the OAuth app out of Testing only when the Google publishing/verification requirements for the selected audience are satisfied.

### Sign-in and account recovery

The login page shows **Continue with Google** as the primary action. Google consent is requested at initial setup, while ordinary later logins use granted scopes without forcing consent. If Google does not return a refresh token on the first connection, use **Reconnect Google Calendar** from Account settings; reconnect is an explicit action and requests consent again.

Account settings shows the connected email and Calendar state. Disconnect requires a checked confirmation and a CSRF-protected POST. It attempts Google token revocation, removes the local connection, and keeps the Django user and all Home Sweet Home data. Disconnect does not delete existing Calendar events, so they may remain in Google Calendar. Normal logout never revokes the connection.

### Talk Later event behavior

When Google Calendar is enabled, saving a scheduled Talk Later topic creates one timed event in the creator’s primary Calendar. The creator remains the organizer even if another household member edits the topic. Other current household members with connected, verified Google email addresses are attendees and receive real invitations through `sendUpdates="all"`. The creator is never added as an attendee, and no organizer event is directly duplicated into attendee calendars.

The event includes the topic title, optional notes, a Home Sweet Home marker, an absolute topic link, the Django time zone, and the configured duration. It has one Google Calendar popup reminder 30 minutes before the event; Calendar defaults remain disabled. Home Sweet Home Web Push remains responsible for the exact-time device reminder. The event does not create Google Meet links.

- Editing title, notes, time, or eligible attendees patches the same event and preserves attendee RSVP state.
- Removing the schedule deletes the remote event with `sendUpdates="all"`.
- Marking done or not done does not alter the Calendar event.
- Deleting a topic first deletes/cancels the remote event. If that fails temporarily, the local topic is retained and can be retried; Google event-not-found is safe to treat as already deleted.
- If the creator has no Calendar connection, a member lacks a connection, or Google is unavailable, the local topic remains usable. The topic detail page exposes safe status, retry, and reconnect actions.

When a household member connects after a topic has been scheduled, Home Sweet Home attempts to refresh future scheduled events in that household so the person can be added as an attendee using the organizer’s credentials.

### Existing-topic synchronization

No Google call is made during migration. After both users connect, synchronize existing future topics explicitly:

```bash
docker compose exec web python manage.py sync_talk_later_google_calendar
```

Useful bounded variants are:

```bash
docker compose exec web python manage.py sync_talk_later_google_calendar --user existing_username
docker compose exec web python manage.py sync_talk_later_google_calendar --household 1 --limit 25
docker compose exec web python manage.py sync_talk_later_google_calendar --force
docker compose exec web python manage.py sync_talk_later_google_calendar --no-future-only
```

The command reports safe counts only; it never prints notes, attendee emails, or OAuth data.

### Deployment and rollout

1. Back up the production database and record the current user IDs, usernames, emails, permissions, and household memberships.
2. Deploy the code and run migrations while Google OAuth remains disabled.
3. Verify existing password login, Grocery Lists, Chores, Talk Later, PWA, and Web Push.
4. Configure the Google Cloud client, Secret Manager secrets, allowlist, and explicit legacy map.
5. Enable Google OAuth and Calendar with `PASSWORD_LOGIN_ENABLED=True`.
6. Complete first Google login for both existing users. Confirm that each maps to the expected existing user and that Calendar access is connected.
7. Run the existing-topic synchronization command for future topics.
8. Test event creation, invitation delivery, edit/reschedule, unschedule, retry, reconnect, marking done, and deletion.
9. Only after both users are successful may production set `PASSWORD_LOGIN_ENABLED=False`. Password hashes remain in the database so fallback can be re-enabled later.

### Troubleshooting

- **Redirect URI mismatch:** Copy the configured redirect URI exactly into Google Cloud and the runtime environment.
- **Account is not linked:** Check the normalized allowlist and `GOOGLE_LEGACY_USER_MAP`, then confirm the mapped Django username exists.
- **No refresh token:** Use the explicit reconnect action, which uses consent; do not repeatedly force consent on ordinary login.
- **Reconnect required:** Google access was revoked, expired, or the encryption key cannot decrypt the stored token. Reconnect the original topic creator’s Google account.
- **Member did not receive an invitation:** The person must be a current member of the same household and have a linked, verified Google email. Cross-household and unconnected users are intentionally excluded.
- **Calendar sync failed:** The Talk Later topic is still saved. Use the topic retry action after fixing the connection or Google API configuration.
- **Encryption key changed:** Old refresh tokens are unrecoverable. Restore the old key from Secret Manager or have each user reconnect.

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

# Google Sign-In and Calendar Deployment Guide

Google Sign-In and Google Calendar synchronization are implemented in this repository. This guide contains the remaining owner actions needed to configure, deploy, and verify the feature. Google Cloud configuration and production secret deployment must be completed by the project owner.

## Current project impact

The repository already has an existing Django user model, household memberships, Talk Later topics, scheduled Web Push reminders, PWA support, Docker, CI/CD, Cloud Run, and Cloud Scheduler. The integration must extend those parts; it must not replace them.

The implementation adds the `google_integration` Django app and scoped changes to settings, URLs, login/account templates, Talk Later model/services/views/templates/admin, dependencies, tests, and README.

Key constraints:

- Existing Django users must be linked, never created automatically.
- Existing user IDs, usernames, passwords, permissions, staff/superuser status, household memberships, and application data must remain unchanged.
- One Calendar event belongs to the topic creator. Other connected household members are invited as attendees; duplicate events must not be written directly to their calendars.
- The current Talk Later Web Push reminders must remain in place. Calendar default reminders must be disabled for these events.
- All OAuth token handling and Calendar API calls stay on the server. Refresh tokens are encrypted before being stored in PostgreSQL.
- No Firebase, service accounts, domain-wide delegation, new task infrastructure, new service worker, or public registration is required.

## Values to prepare before deployment

Prepare these values before enabling Google OAuth in any environment:

| Needed item | Required value or decision |
| --- | --- |
| Approved Google accounts | The verified Google email address for each existing household user allowed to sign in. |
| Existing-user mapping | A confirmed mapping from each approved Google email to the existing Django username. Use this even if the Django email field is incomplete or ambiguous. |
| Local URL | The exact local callback URL, normally `http://localhost:8000/accounts/google/callback/`. |
| Production URL | The exact HTTPS production callback URL, for example `https://your-domain/accounts/google/callback/`. |
| Google OAuth consent audience | Testing initially, with both production users added as test users; decide when the app will move to Production. |
| Password-login rollout | Keep `PASSWORD_LOGIN_ENABLED=True` until both users have successfully linked and tested Google sign-in. |
| Encryption-key custody | A secure location for a generated Fernet key and a recovery procedure. Losing or changing it requires every connected user to reconnect. |
| Secrets deployment | The Secret Manager names and Cloud Run configuration process for Google client credentials and the Fernet key. |

## Google Cloud owner checklist

Complete these actions in Google Cloud before production testing. These are owner actions, not repository changes.

1. Create or select the Google Cloud project that will own the integration.
2. Enable the **Google Calendar API** in that project.
3. Configure Google Auth Platform branding and the consent screen:
   - Set the app name and support/contact details.
   - Choose the appropriate audience.
   - Add the requested scopes only: `openid`, `email`, `profile`, and `https://www.googleapis.com/auth/calendar.events.owned`.
   - While the consent screen is in Testing, add both approved Google accounts as test users.
4. Create a **Web application** OAuth 2.0 client.
5. Add the exact authorized redirect URIs for local and production. The redirect URI must match the configured value character-for-character, including scheme, host, path, and trailing slash.
6. Copy the OAuth client ID and client secret into secret storage only; do not commit them or place them in browser code.
7. Generate a Fernet key using a trusted Python environment, for example:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

8. Store the Fernet key in Secret Manager. Do not regenerate it casually: existing encrypted refresh tokens cannot be decrypted after a key change.
9. Configure the following production values from Secret Manager or the deployment environment:

   ```dotenv
   GOOGLE_OAUTH_ENABLED=True
   GOOGLE_CALENDAR_ENABLED=True
   GOOGLE_OAUTH_CLIENT_ID=...
   GOOGLE_OAUTH_CLIENT_SECRET=...
   GOOGLE_OAUTH_REDIRECT_URI=https://your-domain/accounts/google/callback/
   GOOGLE_ALLOWED_EMAILS=first.person@gmail.com,second.person@gmail.com
   GOOGLE_LEGACY_USER_MAP=first.person@gmail.com:existing_username,second.person@gmail.com:other_username
   GOOGLE_TOKEN_ENCRYPTION_KEY=...
   GOOGLE_CALENDAR_EVENT_DURATION_MINUTES=30
   PASSWORD_LOGIN_ENABLED=True
   ```

10. When ready for broader use, move the OAuth app out of Testing in accordance with Google’s current publishing and verification requirements. Testing authorizations can expire, so users may need to reconnect during that phase.

### Secret Manager names used by continuous deployment

The deployment workflow reads these six Google settings from Secret Manager. Create them before deploying the revision that enables Google OAuth:

| Secret name | Runtime setting |
| --- | --- |
| `home-sweet-home-google-oauth-client-id` | `GOOGLE_OAUTH_CLIENT_ID` |
| `home-sweet-home-google-oauth-client-secret` | `GOOGLE_OAUTH_CLIENT_SECRET` |
| `home-sweet-home-google-oauth-redirect-uri` | `GOOGLE_OAUTH_REDIRECT_URI` |
| `home-sweet-home-google-allowed-emails` | `GOOGLE_ALLOWED_EMAILS` |
| `home-sweet-home-google-legacy-user-map` | `GOOGLE_LEGACY_USER_MAP` |
| `home-sweet-home-google-token-encryption-key` | `GOOGLE_TOKEN_ENCRYPTION_KEY` |

Grant the Cloud Run function runtime service account `roles/secretmanager.secretAccessor` on each secret. Continuous deployment enables OAuth and Calendar support, sets the event duration to 30 minutes, and keeps password sign-in enabled. Do not put any of these values in GitHub Actions variables.

## What is already implemented

### Configuration and dependencies

- Pinned Python 3.13-compatible `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, and `cryptography` dependencies are included.
- `.env.example` contains safe, disabled Google placeholders.
- The `google_integration` app is registered and its routes are available under `/accounts/google/`.
- Startup validates configuration:
  - Google OAuth requires a client ID, client secret, redirect URI, non-empty allowed-email list, and valid Fernet key.
  - Calendar support requires OAuth support.
  - Reject malformed legacy-map entries, duplicate mapped emails, and duplicate mapped usernames.
- Password login remains enabled by default and fully functional while Google OAuth is disabled.

### Identity linking and account management

- `GoogleAccountConnection` is one-to-one with the existing Django user. It stores the Google subject, verified normalized email, encrypted refresh token, granted scopes, connection/login timestamps, Calendar status, safe error state, and reauthorization flag.
- Database uniqueness constraints and indexes protect one Google account per user and one user per Google subject.
- Only refresh tokens are persisted, encrypted with Fernet. Tokens are hidden from Django admin and never rendered or logged.
- Server-side authorization-code OAuth endpoints implement:
  - `start`: creates and stores a random session state plus a safe local `next` path; requests offline access, granted-scope inclusion, account selection, and the required scopes.
  - `callback`: verifies state, exchanges the code, verifies the ID token’s audience, issuer, expiry, subject, verified email, and allowlist membership; then starts a normal Django session.
  - `reconnect`: explicit user action only; uses consent and replaces the refresh token when returned.
  - `status`: exposes safe connection status.
  - `disconnect`: POST + CSRF + confirmation; attempts revocation and removes the connection without deleting the Django user or local data.
- Google identity resolution uses this order: existing matching subject, non-conflicting matching connection email, explicit legacy map, then exactly one case-insensitive Django email match. Unknown or ambiguous users are rejected; no user is inferred by name or created.
- An existing refresh token is preserved when a later Google login returns no new token. A missing token presents an explicit reconnect action.
- Django sessions are rotated after login and only safe local redirect targets are accepted.

### Login and integration UI

- **Continue with Google** is the primary login action, with the required supporting text.
- Username/password remains in a secondary **Use password instead** section while enabled, and `next` is preserved for both methods.
- The account settings page shows connected email, Calendar status, reconnect, disconnect, and safe help/error text.
- Connected users see an unobtrusive state; OAuth never starts automatically.

### Talk Later Calendar synchronization

- `DiscussionTopic` now records event ID/link, calendar ID (`primary`), sync status, safe error, last attempt, and synced time.
- The migration safely marks unscheduled rows `NOT_SCHEDULED` and future scheduled rows `PENDING`; it makes no Google calls.
- The Calendar service layer is in `google_integration`, uses the official client with `cache_discovery=False`, and is separate from views and `shopping`.
- External synchronization runs through `transaction.on_commit()` after local Talk Later persistence succeeds.
- A scheduled topic inserts one event in the creator’s primary Calendar using `sendUpdates="all"`:
  - Summary: `Talk Later: <title>`.
  - Duration: configured event duration, default 30 minutes.
  - Time zone: the Django configured time zone (`Europe/Amsterdam` today).
  - Description: notes when present, “Created by Home Sweet Home”, and an absolute HTTPS topic URL.
  - Private extended property identifying the local topic.
  - Google default reminders disabled with `{"useDefault": false}`.
  - No Google Meet and no arbitrary calendar selection.
- Only other current household members with linked, verified Google emails are invited. Emails are normalized/deduplicated, the creator is excluded, and browser input never controls attendees.
- When a household member connects later, future scheduled household topics are refreshed so that person can become an attendee. A missing connection is a non-blocking warning.
- Editing or rescheduling patches the same event while preserving attendee RSVP states; it never creates a duplicate organizer event.
- Removing a schedule deletes the event with `sendUpdates="all"` and clears metadata only after success.
- Marking a topic done or not done does not change the Calendar event.
- Deleting a local topic first deletes/cancels its event. Event-not-found is treated as success; other deletion failures retain the local topic for safe retry.
- Revoked/invalid credentials mark the connection and topic as requiring reauthorization without rolling back the local Talk Later operation.
- The household-authorized POST/CSRF retry endpoint is `/talk-later/<topic-id>/calendar/retry/`, and it always uses the topic creator’s connection.
- `sync_talk_later_google_calendar` supports safe `--user`, `--household`, `--future-only`, `--limit`, and `--force` recovery/backfill options. It prints counts only.

### Admin, documentation, and tests

- Django admin exposes connection timestamps/status and search by user/email, but never tokens or raw sensitive errors.
- Talk Later admin shows only Calendar status and sync time.
- The README documents setup, linking, event behavior, security, recovery, testing-mode expiry, troubleshooting, and retained Web Push behavior.
- OAuth and Calendar tests are mocked and cover state validation, identity linking, encrypted tokens, password fallback, event creation/patch/deletion, attendee selection, authorization failures, retry authorization, and existing Web Push behavior.

## Rollout plan

1. Back up the production database and confirm the existing usernames, user IDs, emails, permissions, and household memberships.
2. Complete the Google Cloud checklist and configure secrets in the target environment.
3. Deploy the code with `GOOGLE_OAUTH_ENABLED=False` and verify the normal application still works.
4. Run database migrations. Confirm that existing topic records were migrated safely and that no Calendar API calls were made during migration.
5. Enable Google OAuth and Calendar integration with password login still enabled.
6. Complete the first Google login for each approved existing user. Confirm that each Google account links to the expected existing Django user rather than creating one.
7. Run the explicit existing-topic synchronization command for applicable future scheduled topics after both users are connected.
8. Create, edit, unschedule, mark done, retry, and delete test topics. Verify invitations and Web Push behavior.
9. Keep password fallback until Google sign-in, reconnect, and calendar synchronization have been proven for both users. Only then consider setting `PASSWORD_LOGIN_ENABLED=False`; do not remove password hashes.

## Deployment verification

Run the requested repository checks after implementation:

```bash
docker compose config
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
```

Then verify manually:

- Existing password accounts still work while the fallback is enabled.
- Only approved verified Google accounts can sign in, and both map to their existing users with unchanged IDs and memberships.
- Calendar consent occurs on initial connection, not every later login.
- A scheduled topic produces exactly one organizer event and a real invitation for each eligible household attendee; outsiders receive none.
- Editing/rescheduling patches the same event, removing the schedule deletes it, marking done keeps it, and deletion cancels it before removing the local topic.
- Google default reminders are disabled while existing Home Sweet Home Web Push reminders still work.
- API failures leave local topics usable, and retry/reconnect work safely.
- Disconnect preserves the Django user and household data.
- No secrets, tokens, authorization codes, raw API responses, attendee lists, or raw errors appear in Git, templates, admin, or logs.

## Explicitly out of scope

Public registration, automatic user creation, direct per-attendee event duplication, service-account calendar access, Workspace delegation, other Google APIs, Google Meet, free/busy reads, recurring events, calendar selection, browser-selected attendees, custom Calendar reminders, Celery/Redis/Pub/Sub/Cloud Tasks, and a replacement push/service-worker implementation are not part of this work.

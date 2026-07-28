# Home Sweet Home — Google Sign-In and Google Calendar Integration Prompt

You are modifying the existing Django repository:

```text
bahadircolak44/home-sweet-home
```

Inspect the current code before changing anything. Work directly in the existing repository.

The project already contains Django 6, PostgreSQL, existing Django users and household memberships, username/password authentication, Grocery Lists, Household Chores, Talk Later, scheduled Talk Later Web Push reminders, PWA support, Docker, CI/CD, Cloud Run, and Cloud Scheduler.

The current Talk Later implementation already has `DiscussionTopic`, optional `scheduled_for`, done/not-done state, reminder-processing timestamps, and scheduled Web Push delivery.

Do not rebuild the project, replace the user model, create duplicate household memberships, create another service worker, replace Web Push, or rewrite Talk Later from scratch.

Everything added to the repository must be in English: code, settings, templates, labels, validation messages, logs, tests, migrations, admin text, and README documentation.

Do not commit or push changes.

---

## Goal

Implement two connected features.

### 1. Continue with Google

- Users sign in with a Google account.
- The Google account must be linked to the user's existing Django user.
- Preserve existing user IDs, usernames, password hashes, permissions, superuser/staff state, household memberships, and all related data.
- Never auto-create a new Django user.
- The first authorization should request Calendar access as part of the same onboarding flow.
- Later Google logins must not repeatedly show the Calendar consent screen.

Desired flow:

```text
Continue with Google
        ↓
Choose Google account
        ↓
Grant profile and Calendar event access
        ↓
Link the existing Django user
        ↓
Open the Home Sweet Home dashboard
```

### 2. Talk Later → Google Calendar

- When a scheduled Talk Later topic is created, create one event in the creator's primary Google Calendar.
- The topic creator is the organizer.
- Add other current household members as attendees using their linked, verified Google email addresses.
- Send real Calendar invitations using `sendUpdates="all"`.
- Do not write duplicate organizer events directly into every attendee's calendar.
- Update the same event when the topic title, notes, or schedule changes.
- Remove the event when the schedule is removed.
- Remove/cancel the event before deleting the local topic.
- Marking a topic done must not remove the Calendar event.
- Existing Home Sweet Home Web Push reminders must continue to work.

---

## OAuth approach

Use Google's server-side OAuth 2.0 authorization-code flow.

Request only:

```text
openid
email
profile
https://www.googleapis.com/auth/calendar.events.owned
```

Requirements:

- Use `access_type=offline`.
- Use `include_granted_scopes=true`.
- Store a random OAuth `state` value in the Django session and verify it on callback.
- Verify the returned Google ID token on the backend.
- Verify audience, issuer, expiry, `sub`, email, and `email_verified`.
- Use Google `sub` as the stable Google-account identifier.
- Store the refresh token so Calendar calls work when the user is not present.
- Keep all token exchange and Calendar API calls on the backend.
- Never store OAuth tokens in browser storage.
- Do not use Firebase Authentication, Identity Platform, service accounts, or Workspace domain-wide delegation.
- Do not add public registration.

Add maintained Python 3.13-compatible versions of:

- `google-auth`
- `google-auth-oauthlib`
- `google-api-python-client`
- `cryptography`

Pin stable compatible versions and preserve current dependencies.

---

## New Django app

Create:

```text
google_integration
```

Suggested files:

```text
google_integration/
├── admin.py
├── apps.py
├── crypto.py
├── models.py
├── oauth.py
├── services.py
├── urls.py
├── views.py
├── tests.py
└── migrations/
```

Responsibilities:

- Google OAuth login
- Linking existing Django users
- Encrypted refresh-token storage
- Connection/reconnect/disconnect state
- Google Calendar client creation
- Talk Later Calendar synchronization

Do not put Google integration logic into `shopping`.

---

## Configuration

Add these settings and safe placeholders to `.env.example`:

```dotenv
GOOGLE_OAUTH_ENABLED=False
GOOGLE_CALENDAR_ENABLED=False

GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=

GOOGLE_ALLOWED_EMAILS=
GOOGLE_LEGACY_USER_MAP=
GOOGLE_TOKEN_ENCRYPTION_KEY=

GOOGLE_CALENDAR_EVENT_DURATION_MINUTES=30
PASSWORD_LOGIN_ENABLED=True
```

### `GOOGLE_ALLOWED_EMAILS`

Comma-separated allowlist of the only Google accounts allowed to sign in.

Example:

```dotenv
GOOGLE_ALLOWED_EMAILS=first.person@gmail.com,second.person@gmail.com
```

Normalize emails to lowercase. Reject every account outside the allowlist. Require a non-empty allowlist whenever Google OAuth is enabled.

### `GOOGLE_LEGACY_USER_MAP`

Maps verified Google emails to existing Django usernames.

Example:

```dotenv
GOOGLE_LEGACY_USER_MAP=first.person@gmail.com:bahadir,second.person@gmail.com:pinar
```

Validate malformed entries, duplicate emails, and duplicate usernames at startup. Never create users from this mapping.

### `GOOGLE_TOKEN_ENCRYPTION_KEY`

A Fernet key used to encrypt refresh tokens before storing them in PostgreSQL.

Requirements:

- Validate it at startup.
- Never generate it automatically during application startup.
- Never log or commit it.
- Document that changing or losing it requires every user to reconnect.

### Startup validation

When `GOOGLE_OAUTH_ENABLED=True`, fail startup clearly if client ID, client secret, redirect URI, allowed emails, or encryption key are missing.

When `GOOGLE_CALENDAR_ENABLED=True`, require Google OAuth to be enabled.

Keep password login configurable through `PASSWORD_LOGIN_ENABLED`.

---

## GoogleAccountConnection model

Create `GoogleAccountConnection` with:

- `user`: OneToOneField to the existing Django user
- `google_subject`: unique CharField
- `email`: EmailField
- `email_verified`: BooleanField
- `encrypted_refresh_token`: TextField
- `granted_scopes`: JSONField, default list
- `connected_at`
- `updated_at`
- `last_login_at`
- `last_calendar_success_at`: nullable
- `reauthorization_required`: BooleanField, default `False`
- `last_error`: blank TextField, safely truncated

Rules:

- One Google account per Django user.
- One Django user per Google account.
- Store only the encrypted refresh token; do not persist ordinary access tokens unless unavoidable.
- Normalize email to lowercase.
- Hide token contents in admin.
- Add useful indexes and a normal migration.
- Do not replace the Django user model.

---

## Refresh-token encryption

Implement a small Fernet helper.

- Encrypt before saving.
- Decrypt only when constructing Google credentials.
- Raise safe integration errors if decryption fails.
- Never include secrets in exception messages.
- Use a deterministic test key in tests.
- Never silently create a replacement encryption key.

---

## Existing-user linking

After verifying Google's ID token, resolve the existing Django user in this order:

1. Existing connection with the same `google_subject`.
2. Existing connection with the same normalized email, when not linked to a conflicting subject.
3. Username from `GOOGLE_LEGACY_USER_MAP`.
4. Exactly one Django user whose `email` matches case-insensitively.

If no safe match exists:

```text
This Google account is not linked to a Home Sweet Home user.
```

Do not create a user and do not guess by name.

Before linking:

- Require allowlisted email.
- Require `email_verified=True`.
- Ensure the Django user is not linked to another Google subject.
- Ensure the Google subject is not linked to another user.

After linking:

- Preserve the existing user's primary key and all existing relationships.
- Set `user.email` only when blank or when the explicit legacy map is being used.
- Fill blank first/last names from Google profile data, but never overwrite existing non-empty values.
- Create a normal Django authenticated session using `django.contrib.auth.login`.

---

## OAuth routes

Use namespace `google_integration`.

Suggested routes:

```text
/accounts/google/start/
/accounts/google/callback/
/accounts/google/reconnect/
/accounts/google/status/
/accounts/google/disconnect/
```

### Start

- Accept an optional safe local `next` URL.
- Generate and store OAuth state.
- Store the safe post-login redirect in session.
- Use offline access, granted-scope inclusion, and account selection.
- Do not force consent during every login.

### Callback

- Validate state.
- Exchange the authorization code server-side.
- Verify the ID token.
- Resolve and link the existing user.
- Preserve the existing encrypted refresh token if a later login returns no new refresh token.
- If no refresh token is returned and none is stored, show a reconnect action that uses explicit consent.
- Store granted scopes.
- Rotate the Django session key.
- Redirect only to a safe local URL or dashboard.
- Never log tokens, authorization codes, or raw OAuth responses.

### Reconnect

- Trigger only after explicit user action.
- Use `prompt=consent`.
- Replace the encrypted refresh token when returned.
- Clear `reauthorization_required`.
- Retry future pending/failed Calendar syncs created by this user.

### Disconnect

- Require POST, CSRF, and confirmation.
- Attempt Google token revocation.
- Remove/clear the connection without deleting the Django user or application data.
- Do not revoke on normal logout.
- Existing Google Calendar events may remain after disconnect.
- Keep password login available during rollout to prevent lockout.

---

## Login page

Update the existing login page.

Primary action:

```text
Continue with Google
```

Supporting text:

```text
Sign in with your approved Google account and connect Google Calendar.
```

Requirements:

- Make Google the prominent action.
- Preserve username/password as a temporary fallback.
- Put password fields behind a secondary section such as `Use password instead`.
- Show/hide fallback through `PASSWORD_LOGIN_ENABLED`.
- Default fallback to enabled.
- Do not reset existing passwords.
- When Google OAuth is disabled, password login remains fully usable.
- Preserve `next` for both methods.

After both production users are linked and tested, production may set:

```dotenv
PASSWORD_LOGIN_ENABLED=False
```

The password hashes must still remain intact so fallback can be re-enabled through configuration.

---

## One-time connection UI

Do not permanently show a large Calendar setup button.

- Valid connection: subtle text, `Google Calendar connected as user@gmail.com`.
- Password login without connection: `Connect Google Calendar`.
- Revoked/invalid token: `Reconnect Google Calendar`.
- After success, the large setup action disappears.
- Never start OAuth automatically on page load.

Add a small account/integration settings page showing:

- Connected email
- Calendar access status
- Reconnect
- Disconnect
- Safe error/help text

---

## Extend DiscussionTopic

Add Calendar synchronization metadata to `DiscussionTopic`:

- `google_calendar_event_id`: blank CharField
- `google_calendar_html_link`: blank URLField
- `google_calendar_id`: CharField, default `primary`
- `calendar_sync_status`: TextChoices
- `calendar_sync_error`: blank TextField
- `calendar_last_attempt_at`: nullable
- `calendar_synced_at`: nullable

Statuses:

- `NOT_SCHEDULED`
- `PENDING`
- `SYNCED`
- `FAILED`
- `REAUTHORIZATION_REQUIRED`

Migration requirements:

- Existing rows migrate safely.
- Unscheduled topics become `NOT_SCHEDULED`.
- Existing scheduled future topics may become `PENDING`.
- Do not call Google in a migration.
- Provide a management command to sync existing future topics explicitly.

The topic's existing `created_by` is always the Calendar organizer, even when another household member edits the topic.

---

## Google Calendar client

Build Google credentials from:

- Client ID
- Client secret
- Decrypted refresh token
- Google's token endpoint
- Granted scopes

Use the official Calendar API client with `cache_discovery=False`.

If token refresh fails due to revocation or invalid credentials:

- Set connection `reauthorization_required=True`.
- Mark affected topic `REAUTHORIZATION_REQUIRED`.
- Keep the local Talk Later operation successful.
- Show a reconnect action.

Never log credential objects or raw API responses.

---

## Calendar event body

Create one timed event in the creator's primary Calendar.

- Summary: `Talk Later: <topic title>`
- Start: `topic.scheduled_for`
- End: start plus `GOOGLE_CALENDAR_EVENT_DURATION_MINUTES`
- Time zone: Django `TIME_ZONE`, currently `Europe/Amsterdam`
- Description:
  - notes when present
  - `Created by Home Sweet Home`
  - absolute HTTPS URL to the Talk Later topic
- Attendees: linked verified emails of other current household members
- `guestsCanModify=False`
- `guestsCanInviteOthers=False`
- `guestsCanSeeOtherGuests=True`
- No Google Meet
- Add a private extended property identifying the Home Sweet Home topic for diagnostics

Use:

```json
{"useDefault": false}
```

for Calendar reminders. Home Sweet Home already sends the exact-time Web Push reminder, so Google Calendar default reminders should be disabled to prevent duplicate phone notifications. The event and invitation still exist.

---

## Attendee selection

- The creator is organizer and must not also be a guest.
- Select current members of the same household.
- Exclude the creator.
- Use only linked, verified Google emails.
- Normalize and deduplicate emails.
- Never invite cross-household users.
- Never accept attendee IDs/emails from browser input.

If a household member has not connected Google:

- Still create the organizer's event.
- Show a non-blocking warning that the member was not invited.
- Do not silently use an unverified local email.

When that member later connects, attempt to refresh future scheduled events in the household so they can be added as an attendee, using each topic organizer's credentials.

---

## Synchronization services

Keep Calendar synchronization in services, not views.

Suggested functions:

- `build_calendar_service(connection)`
- `build_topic_event_body(topic)`
- `calendar_attendees_for_topic(topic)`
- `create_topic_calendar_event(topic)`
- `update_topic_calendar_event(topic)`
- `delete_topic_calendar_event(topic)`
- `sync_topic_calendar_event(topic)`
- `sync_future_topics_for_user(user)`
- `sync_household_future_topics(household)`

Use `transaction.on_commit()` so external calls happen only after the local transaction succeeds.

### Create

1. Save local topic.
2. Mark sync `PENDING`.
3. After commit call `events.insert(calendarId="primary", ..., sendUpdates="all")`.
4. Store event ID, HTML link, and sync timestamps.
5. Keep the local topic if Google fails; mark failed/reconnect-required and show Retry.

### Update

- Patch the existing event; never insert a duplicate.
- Use `events.patch(..., sendUpdates="all")`.
- Preserve attendee RSVP states rather than resetting accepted/declined responses.
- If a topic becomes scheduled for the first time, create the event.

### Remove schedule

- Delete the existing event with `sendUpdates="all"`.
- Clear event metadata only after successful deletion.
- If deletion fails, retain event ID and a retryable failure state.

### Done/not done

- Do not modify the Calendar event solely because `is_done` changed.

### Delete topic

If an event exists:

1. Attempt to delete it using `sendUpdates="all"`.
2. Treat Google event-not-found as success.
3. Delete the local topic only after successful/absent Calendar deletion.
4. On temporary API, network, or authorization failure, preserve the local topic and show a retryable safe error.

This stricter delete flow avoids orphaned Calendar invitations after the local topic disappears.

---

## Calendar status UI

On topic detail, show a compact Calendar section when integration is enabled.

States:

- `Not scheduled — no Calendar event`
- `Calendar sync pending`
- `Added to Google Calendar`
- `Calendar sync failed`
- `Reconnect Google Calendar to continue syncing`

Actions:

- `Open in Google Calendar`
- `Retry Calendar Sync`
- `Connect Google Calendar`
- `Reconnect Google Calendar`

Mutating actions use POST and CSRF. Do not show raw Google errors. Keep the Talk Later record usable when Calendar is unavailable.

Add a household-authorized POST endpoint:

```text
/talk-later/<topic-id>/calendar/retry/
```

Always sync using the topic creator's Google connection; an editor must not become organizer.

---

## Existing-topic management command

Add:

```bash
python manage.py sync_talk_later_google_calendar
```

Options:

- `--user USERNAME`
- `--household HOUSEHOLD_ID`
- `--future-only` default true
- `--limit`
- optional explicit force flag

Requirements:

- Sync future scheduled topics.
- Skip already-synced unchanged topics unless forced.
- Print safe counts only.
- Never print notes, tokens, or attendee emails.

Do not add Celery, Redis, Pub/Sub, Cloud Tasks, or a new Scheduler job. Attempt immediate sync and provide explicit retry/management-command recovery.

---

## Authentication and authorization separation

The same first-time Google flow requests identity and Calendar scopes, but keep the concepts separated in code:

- Authentication proves who the user is.
- Authorization grants Calendar access.

A user remains a valid Home Sweet Home user if Calendar access later fails. Revocation must never delete or disable the Django account. Password login can still use an already-linked Calendar connection.

---

## Security and privacy

- Use the allowed-email list.
- Never auto-register unknown users.
- Verify ID tokens server-side.
- Use OAuth state.
- Encrypt refresh tokens.
- Keep client secret and encryption key out of Git.
- Validate `next` redirects as local/same-origin.
- Use HTTPS in production.
- Never log authorization codes, ID tokens, access tokens, refresh tokens, client secret, encryption key, attendees, or full API responses.
- Sanitize errors.
- Keep CSRF protection.
- Add explicit disconnect functionality.

---

## Admin

Register `GoogleAccountConnection`.

Show user, Google email, connected time, last login, last Calendar success, and reauthorization state. Search by username/email. Hide token contents completely.

Extend `DiscussionTopic` admin with Calendar status and synced time without exposing raw errors or credentials.

---

## Tests

Mock every Google OAuth and Calendar call.

Cover at least:

1. OAuth start stores state and safe next URL.
2. Invalid state is rejected.
3. Unverified email is rejected.
4. Non-allowlisted email is rejected.
5. Google account links to the mapped existing user.
6. User ID, household membership, permissions, and related data remain unchanged.
7. Unknown users are not auto-created.
8. Existing refresh token is preserved when a later login returns no new token.
9. Refresh token is encrypted at rest.
10. Google login creates a normal Django session.
11. Password login works when enabled.
12. Scheduled topic inserts one organizer event and invites only other household members.
13. `sendUpdates="all"` is used.
14. Creator is not duplicated as attendee.
15. Cross-household users are excluded.
16. Update patches the same event.
17. Removing schedule deletes the event.
18. Topic deletion is blocked if Calendar deletion fails.
19. Event-not-found allows local deletion.
20. Calendar failure does not roll back topic create/update.
21. Revoked credentials mark reauthorization required.
22. Marking done keeps the Calendar event.
23. Retry endpoint is household-authorized.
24. Existing Web Push reminder behavior is unchanged.

Use Django tests and `unittest.mock`. Do not make real Google calls or add browser automation.

---

## README

Document:

- Continue with Google
- Existing-user linking
- Allowed emails and legacy username mapping
- Calendar scope and offline access
- Organizer/attendee behavior
- Why one event is created instead of direct duplicates
- Create/update/unschedule/delete rules
- Web Push versus Calendar invitations
- Local Google OAuth setup
- Google Cloud setup
- Exact redirect URI matching
- Secret Manager deployment
- Fernet key generation
- First-login procedure for both existing users
- Reconnect/disconnect
- Calendar status and retry
- Existing-topic sync command
- Testing-mode authorization expiry warning
- Troubleshooting for redirect mismatch, missing mapping, no refresh token, revoked access, missing invitation, sync failure, and changed encryption key

Preserve current Grocery Lists, Chores, Talk Later, Web Push, PWA, Docker, Cloud Run, Cloud Scheduler, CI/CD, migrations, and superuser docs.

---

## Owner actions required in the final implementation summary

The coding agent must clearly state that the project owner still needs to:

1. Enable Google Calendar API.
2. Configure Google Auth Platform branding, audience, and scopes.
3. Add the two Google accounts as test users during testing.
4. Create a Web application OAuth client.
5. Add exact local and production redirect URIs.
6. Generate a Fernet token-encryption key.
7. Configure allowed emails and legacy-user mappings.
8. Store production secrets in Secret Manager.
9. Run migrations and deploy.
10. Complete first Google login for both existing users.
11. Test invitation creation, update, unschedule, and delete.
12. Move the OAuth app out of Testing when appropriate.

Do not claim external Google Cloud configuration was completed by the coding agent.

---

## Out of scope

Do not implement:

- Public Google registration
- Automatic Django user creation
- Direct duplicate event writes to every attendee calendar
- Service-account access to personal calendars
- Workspace domain-wide delegation
- Gmail, Drive, Contacts, Photos, or other Google APIs
- Google Meet
- Reading unrelated personal Calendar events
- Free/busy lookup
- Recurring Calendar events
- Calendar selection
- User-selected attendees
- Custom Calendar reminder preferences
- Celery, Redis, Pub/Sub, or Cloud Tasks
- Another service worker or push system
- Removal of existing users or household data

---

## Verification

Run:

```bash
docker compose config
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
```

Manually verify:

1. Existing username/password accounts still work.
2. Continue with Google is the primary login action.
3. Unapproved accounts are rejected.
4. Both approved Google accounts map to the correct existing users.
5. User IDs and household memberships remain unchanged.
6. Calendar consent appears during first setup, not every login.
7. Scheduled topic creates one event in the creator's primary Calendar.
8. The other household member receives a real invitation.
9. No outsider is invited.
10. Event content, duration, and topic link are correct.
11. Google default reminders are disabled.
12. Existing Home Sweet Home Web Push still works.
13. Editing/rescheduling updates the same event.
14. Removing schedule removes the event.
15. Marking done keeps the event.
16. Deleting removes/cancels the event and sends updates.
17. API failure leaves local topics usable.
18. Retry and reconnect work.
19. Disconnect preserves Django users and household data.
20. No secrets appear in logs, templates, admin, or Git.
21. Existing Grocery Lists, Chores, Talk Later, PWA, and Web Push tests pass.
22. No Turkish text was added.

At the end, provide a concise implementation summary with files, dependencies, models/migration, OAuth routes, account-linking logic, Calendar rules, environment variables, tests/results, exact manual Google Cloud steps, and assumptions.

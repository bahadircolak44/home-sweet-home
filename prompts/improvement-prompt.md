You are modifying the existing Django project:

home-sweet-home

Repository:

bahadircolak44/home-sweet-home

Inspect the existing implementation before changing anything. Do not rebuild the
application from scratch, do not replace working PWA functionality, and do not
create a second service worker.

Everything added to the repository must remain in English, including code,
templates, UI text, validation messages, tests, comments, admin labels, and
README documentation.

Do not commit or push changes.

# Goal

Add standards-based Web Push notifications to the existing Home Sweet Home PWA.

A household member must be able to enable notifications separately on each
installed device or browser. When one household member changes a grocery list,
the other household members with active push subscriptions must receive a
notification.

Do not notify the user who performed the change.

Use the existing:

- Django 6 application
- PostgreSQL database
- Authentication and household memberships
- Grocery list services
- Existing root-scoped `/service-worker.js`
- Existing `static/js/app.js`
- Existing PWA manifest and application icons
- Existing Docker and Cloud Run deployment structure

Do not introduce Firebase application configuration, Celery, Redis, Cloud Tasks,
a separate notification server, or a frontend framework.

# 1. Dependencies

Add compatible pinned versions of:

- `pywebpush`
- `py-vapid`

Use the current maintained releases compatible with Python 3.13.

Keep all existing dependencies.

# 2. Django application

Create a small Django app named:

push_notifications

Suggested structure:

push_notifications/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── services.py
├── urls.py
├── views.py
├── tests.py
└── migrations/

Add it to `INSTALLED_APPS`.

Keep notification-specific code out of the shopping views and templates where
possible.

# 3. Push subscription model

Create a `PushSubscription` model with:

- `user`: ForeignKey to Django user
- `endpoint`: TextField, unique
- `p256dh`: TextField
- `auth`: TextField
- `user_agent`: TextField, blank
- `created_at`
- `updated_at`
- `last_seen_at`

Requirements:

- One row represents one browser/device subscription.
- A user may have multiple subscriptions.
- The endpoint must be globally unique.
- Subscribing an endpoint that already exists must update it and assign it to
  the currently authenticated user.
- Do not add a household foreign key; determine recipients through the user's
  current household membership.
- Add useful `__str__`, ordering, and admin configuration.
- Never show complete endpoints or cryptographic keys in the admin list page.
- Add a normal new migration. Do not modify or squash old migrations.

# 4. Configuration

Add these settings:

- `PUSH_NOTIFICATIONS_ENABLED`
- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY_PATH`
- `VAPID_SUBJECT`

Example local values:

```dotenv
PUSH_NOTIFICATIONS_ENABLED=True
VAPID_PUBLIC_KEY=replace-with-application-server-key
VAPID_PRIVATE_KEY_PATH=private_key.pem
VAPID_SUBJECT=mailto:replace-with-contact-email@example.com

Requirements:

Parse PUSH_NOTIFICATIONS_ENABLED as a boolean.
Resolve a relative VAPID_PRIVATE_KEY_PATH relative to BASE_DIR.
Allow an absolute private-key path in production.
When push is enabled, fail startup with a clear configuration error if any
required VAPID setting is missing.
The private key must never be returned to the browser, rendered into HTML,
logged, committed, or stored in the database.
The public key may be exposed to authenticated pages.
Add private_key.pem, public_key.pem, and similar VAPID key files to
.gitignore and .dockerignore.
Add safe placeholder values to .env.example.
5. Subscription endpoints

Add authenticated, CSRF-protected endpoints under:

/notifications/

Implement:

POST /notifications/subscribe/
POST /notifications/unsubscribe/
POST /notifications/test/
Subscribe

Accept the JSON representation of a browser PushSubscription:

{
  "endpoint": "https://...",
  "keys": {
    "p256dh": "...",
    "auth": "..."
  }
}

Requirements:

Require authentication.
Require POST.
Require CSRF.
Validate the JSON structure and field lengths.
Require an HTTPS endpoint.
Upsert by endpoint.
Associate the subscription with the current user.
Save a shortened user-agent value.
Return a small JSON success response.
Do not return stored cryptographic data.
Unsubscribe

Requirements:

Require authentication, POST, and CSRF.
Accept the endpoint.
Delete only a subscription belonging to the current user.
Be idempotent if it no longer exists.
Test notification

Requirements:

Require authentication, POST, and CSRF.
Send a test notification only to the current browser subscription supplied
by the request.
Verify that the subscription belongs to the current user.
Use a message such as:
Title: Home Sweet Home
Body: Notifications are working on this device.
Return a clear JSON response.
Do not send a real network request in automated tests; mock the push library.
6. Dashboard notification UI

Add a compact notification settings card to the authenticated dashboard.

Possible states:

Push unsupported:
Notifications are not supported by this browser.
iOS and not running as an installed Home Screen app:
Install Home Sweet Home on your Home Screen before enabling notifications.
Permission not requested:
Enable Notifications
Permission granted and subscribed:
Notifications are enabled on this device.
Actions:
Send Test Notification
Disable Notifications
Permission denied:
Notifications are blocked. Enable them from your browser or device settings.

Requirements:

Never request permission automatically on page load.
Request permission only after the user presses Enable Notifications.
Hide notification controls when PUSH_NOTIFICATIONS_ENABLED=False.
Use feature detection for:
serviceWorker
PushManager
Notification
Do not rely only on browser user-agent detection.
Keep iOS-specific text limited to installation guidance.
Preserve the existing warm visual design and mobile layout.
Add accessible status text using aria-live.
7. Browser subscription logic

Extend the existing static/js/app.js; do not create a competing service-worker
registration flow.

Implement:

Wait for the existing service worker to become ready.
Read the public VAPID key supplied by Django.
Convert the URL-safe Base64 key to Uint8Array.
Check registration.pushManager.getSubscription().
On enable:
Request notification permission from the explicit click handler.
Call pushManager.subscribe() with:
userVisibleOnly: true
applicationServerKey
POST subscription.toJSON() to Django.
On disable:
Delete the server-side subscription.
Call subscription.unsubscribe().
On test:
POST the active endpoint to the test endpoint.
Keep the UI state synchronized after reload.
Display safe, user-friendly failures without exposing endpoints or keys.
Include the CSRF token in all fetch requests.

Each device and browser must create its own subscription.

Do not automatically subscribe a user simply because the PWA is installed.

8. Service worker push handling

Extend the existing templates/service-worker.js.

Preserve the current conservative static-asset caching behavior.

Add a push event handler that:

Safely parses JSON payloads.
Uses fallback title and body values if payload data is missing.
Calls self.registration.showNotification().
Uses the existing application icon.
Supports:
title
body
url
tag
Stores the target URL under notification data.
Uses a stable tag per grocery list.
Does not cache notification payloads.
Does not cache authenticated HTML.
Does not cache mutation responses.
Does not fetch grocery data in the background.

Add a notificationclick handler that:

Closes the notification.
Validates that the target is a same-origin relative URL.
Searches existing window clients.
Focuses an existing Home Sweet Home window when possible.
Navigates that window to the target URL when necessary.
Otherwise opens a new window with clients.openWindow().
Falls back to / for malformed or missing URLs.

Increment the current static cache version only when needed.

9. Backend delivery service

Implement notification delivery in push_notifications/services.py.

Provide small functions similar to:

send_push_notification(subscription, payload)
send_to_household_members(...)
remove_expired_subscription(...)

Use pywebpush.webpush.

Construct subscription information as:

{
    "endpoint": subscription.endpoint,
    "keys": {
        "p256dh": subscription.p256dh,
        "auth": subscription.auth,
    },
}

Use:

The configured private-key path
{"sub": settings.VAPID_SUBJECT} as VAPID claims
A short, reasonable TTL
A short network timeout where supported

Requirements:

Catch WebPushException.
Never allow a push error to roll back or fail a grocery-list operation.
Remove subscriptions when the push service returns HTTP 404 or 410.
Log other failures without logging the full endpoint, auth key, p256dh key,
payload secrets, or private key.
Sending to zero subscriptions must be a no-op.
Do not retry indefinitely.
Do not implement a background queue in this iteration.
10. Notification recipients

For a grocery change:

Determine the grocery list's household.
Find other users in the same household.
Exclude the actor entirely, including all devices owned by the actor.
Send to every active subscription belonging to the remaining household
members.
Never send across household boundaries.

Capture primitive values such as IDs, names, and URL strings before scheduling
callbacks. Do not pass deleted or stale model objects into delayed callbacks.

11. Transaction behavior

Notifications must be registered with transaction.on_commit() so a message is
sent only after the database transaction succeeds.

The existing shopping service methods are already transactional. Extend them
carefully rather than moving business logic back into views.

For list operations currently implemented directly in views, either:

introduce small service functions, or
register an explicit transaction.on_commit() callback after a successful
save/delete.

Push delivery must never happen for a rolled-back database change.

12. Notification events

Notify other household members for:

Grocery list created
Grocery list renamed or icon changed
Grocery list deleted
Grocery list completed
Grocery item added
Grocery item edited
Grocery item deleted
Grocery item marked as purchased
Grocery item returned to remaining items

Example messages:

Bahadir added 2× Milk to Albert Heijn.
Bahadir marked Milk as purchased.
Bahadir updated an item in Albert Heijn.
Bahadir completed Albert Heijn.

Requirements:

Use the actor's full name when available, otherwise username.
Include item quantity when greater than one.
Do not include item descriptions.
Do not include product URLs.
Do not include internal database IDs in visible text.
Item/list names must be treated as plain text.
Keep title and body concise.
Use a tag such as grocery-list-<id> so recent changes for one list may
replace older notifications instead of creating excessive notification
clutter.
The target URL should normally open the changed grocery list.
For a deleted or completed list, use the most appropriate existing module or
history URL.
13. Privacy and lifecycle
A push subscription endpoint must be treated as sensitive application data.
Do not expose subscriptions through ordinary pages.
Do not include subscriptions in logs.
Add a clearly visible Disable Notifications action.
If an endpoint is registered later by another authenticated user in the same
browser, update ownership to the new user.
Document that notification permission and subscription are per device.
Document that logging out does not necessarily revoke operating-system
notification permission; users should use Disable Notifications when
removing a personal device.
Do not send item descriptions or product URLs to lock-screen notifications.
14. Django Admin

Register PushSubscription.

Admin requirements:

Show user, created time, updated time, and shortened endpoint host.
Search by username.
Filter by created/updated date.
Keep key fields read-only or hidden.
Provide no action that prints full subscription secrets.
Allow an administrator to delete obsolete subscriptions.
15. Tests

Add a focused test set without spending excessive effort.

Use Django's built-in test framework and mock pywebpush.

Cover:

Subscription creation belongs to the authenticated user.
Re-subscribing the same endpoint updates rather than duplicates it.
A user cannot unsubscribe another user's endpoint.
Notification recipients are limited to other members of the same household.
The actor's subscriptions are excluded.
A shopping change schedules delivery only after commit.
HTTP 404/410 push responses remove stale subscriptions.
Push failures do not fail the grocery operation.
The test-notification endpoint cannot target another user's subscription.
Completed-list and item events create the expected safe payload.

Do not add Selenium, Playwright, browser automation, or real external push calls.

16. README

Update the English README with:

How Web Push works in this project
The per-device permission requirement
Android installation and notification steps
iPhone/iPad Home Screen installation requirement
Local VAPID key generation
Local environment variables
Cloud Run Secret Manager deployment
How to send a test notification
How to disable notifications
Troubleshooting for denied permissions
A warning not to regenerate VAPID keys after users subscribe
A warning not to commit private keys
A statement that full offline functionality remains out of scope

Keep the existing Docker, migration, superuser, PWA, and deployment documentation.

17. Verification

Run:

docker compose config
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput

Manually verify:

Existing PWA installation still works.
Existing static caching still works.
The browser does not request permission on page load.
Enable Notifications creates one subscription.
Re-enabling does not create duplicates.
Test Notification reaches the current device.
Changes by User A notify User B.
User A does not receive their own change notification.
Users outside the household receive nothing.
Clicking a notification opens the correct grocery page.
Disabling notifications removes the server record.
A push-provider failure does not break grocery changes.
No authenticated HTML is cached.
No secret or complete endpoint appears in logs.
No Turkish text has been added.

At the end, provide a concise summary of:

Files created and changed
Model and migration added
New routes
Environment variables
Notification events
Tests and results
Manual steps still required from the project owner
# Home Sweet Home — Talk Later Implementation Prompt

You are modifying the existing Django repository `bahadircolak44/home-sweet-home`.

Implement this task after Household Chores. Inspect the current repository first and work directly in it.

The project already contains Django templates, PostgreSQL, household memberships, Grocery Lists, Household Chores, a dashboard, HTMX, PWA installation, working Web Push subscriptions/delivery, a root-scoped service worker, Docker, CI/CD, and Cloud deployment.

Do not rebuild the project, duplicate household authorization, create another service worker, create another push-subscription system, or replace working modules.

Everything added must be in English: code, templates, labels, messages, comments, tests, migrations, admin text, and README documentation.

Do not commit or push changes.

## Goal

Add a simple household module named **Talk Later**.

It stores topics household members want to discuss later.

Examples:

- `Discuss the holiday budget`
- `Choose the new dining table`
- `Call the vet together`
- `Plan next weekend`

A topic may optionally have a scheduled date and time. At that time, send a Web Push reminder to every subscribed device belonging to current members of the household, including the topic creator.

A topic is simply not done or done.

Core flow:

1. Add a topic.
2. Optionally choose when to discuss it.
3. Receive a reminder at that time.
4. Mark it done after discussing it.

Do not build a complete calendar, meeting system, notes platform, or project-management tool.

## Naming

Use:

- Django app: `talk_later`
- User-facing module: `Talk Later`
- Main model: `DiscussionTopic`
- Icon: `💬`

Description:

```text
Save topics to discuss together and get reminded at the right time.
```

## Model

Create `DiscussionTopic`.

Fields:

- `household`: ForeignKey to `Household`
- `title`: CharField, maximum about 180 characters
- `notes`: TextField, blank
- `scheduled_for`: nullable DateTimeField
- `is_done`: BooleanField, default `False`
- `created_by`: ForeignKey to user
- `completed_by`: nullable ForeignKey to user
- `created_at`
- `updated_at`
- `completed_at`: nullable DateTimeField
- `reminder_claimed_at`: nullable DateTimeField
- `reminder_processed_at`: nullable DateTimeField
- `reminder_sent_at`: nullable DateTimeField

Rules:

- Trim title and notes.
- Reject empty/whitespace-only titles.
- Limit notes to about 2,000 characters through form validation.
- `scheduled_for` is optional.
- Store timezone-aware datetimes.
- Use the project's configured `Europe/Amsterdam` timezone for form interpretation and display.
- Unscheduled topics are valid.
- Marking done sets `completed_by` and `completed_at=timezone.now()`.
- Marking not done clears completion metadata.
- Done topics are not eligible for reminders.
- Reopening a topic does not automatically resend an already processed reminder.
- Changing `scheduled_for` clears all reminder claim/processed/sent fields.
- Removing `scheduled_for` also clears those fields.
- Editing only title or notes does not resend an old reminder.
- Deleting a topic prevents future processing.
- Add indexes for household/done filtering, due-reminder lookup, and upcoming ordering.

Do not add recurrence, participants, priority, multiple reminders, snooze, or attachments.

## Reminder-state meaning

Use:

- `reminder_claimed_at`: a worker temporarily claimed the topic.
- `reminder_processed_at`: the attempt completed and must not run again for the current schedule.
- `reminder_sent_at`: at least one device received a successful push-delivery response.

Rules:

- A stale claim may retry after about 10 minutes.
- A processed topic does not run again.
- A topic with no active subscriptions may be processed without `reminder_sent_at`.
- Provider failures must not retry forever.
- Rescheduling explicitly creates a new reminder opportunity.
- These fields are internal and not editable by users.

Keep this as a small reliability mechanism, not a general queue.

## Authorization

Reuse existing household-membership authorization.

Every user-facing endpoint must ensure:

1. The user is authenticated.
2. The topic belongs to the user's current household.

All members of the household may create, edit, delete, complete, and reopen topics.

Never trust IDs from URLs or forms. Filter by household before object lookup. Use POST and CSRF for state changes. Use the project's existing friendly handling for users without a household.

The internal scheduler endpoint uses a separate secret token, not normal user authentication.

## Form and datetime handling

Create a `DiscussionTopicForm`.

User fields:

- Title
- Optional notes
- Optional scheduled date and time

A single `datetime-local` input is acceptable if cleaner.

Requirements:

- Use Django form validation.
- Convert local input to a timezone-aware datetime.
- Display existing values in local time.
- New topics must reject a time clearly in the past.
- Allow about one minute of tolerance for clock/submit delay.
- Use this clear error:

```text
Choose a future date and time, or leave the reminder empty.
```

Business validation must not exist only in JavaScript.

## Services

Create `talk_later/services.py` with small functions such as:

- `create_topic`
- `update_topic`
- `toggle_topic`
- `delete_topic`
- `upcoming_topics_for_user`
- `completed_topics_for_user`
- `claim_due_topics`
- `process_due_reminders`

Use `transaction.atomic` where appropriate. Keep views thin. Use a domain exception such as `InvalidDiscussionOperation`.

Do not use signals. Do not send immediate push notifications when a topic is created or edited. Push only when its scheduled reminder is due.

## Routes

Use namespace `talk_later`.

Suggested user routes:

```text
/talk-later/
/talk-later/new/
/talk-later/<topic-id>/
/talk-later/<topic-id>/edit/
/talk-later/<topic-id>/toggle/
/talk-later/<topic-id>/delete/
```

Internal scheduler route:

```text
/internal/talk-later/process-reminders/
```

Use named URLs and `reverse`. Do not add a REST API.

## Dashboard

Add a third active dashboard card:

- Icon: `💬`
- Title: `Talk Later`
- Description: `Save topics to discuss together and get reminded at the right time.`
- Pending-topic count
- Next scheduled topic time, when available
- Action: `Open Talk Later`

Keep Grocery Lists and Household Chores unchanged. Compute summaries efficiently. If nothing is scheduled, show `No reminder scheduled`.

## Navigation

Add Talk Later to authenticated navigation.

Modules:

- Home
- Grocery Lists
- Household Chores
- Talk Later

Keep mobile navigation usable around 320px. Compact labels/icons are acceptable. Preserve focus styles and prevent the navigation from covering content.

## Main page

Create `/talk-later/`.

Show:

- `Talk Later`
- Short explanation
- `Add Topic`
- Compact quick-add form
- Pending topics grouped by time
- Completed topics as a secondary section

Recommended pending groups:

1. `Overdue`
2. `Today`
3. `Next 7 Days`
4. `Later`
5. `Unscheduled`

Rules:

- Do not build month/week calendar views.
- Omit empty groups.
- Sort scheduled topics by `scheduled_for`.
- Sort unscheduled topics by newest update.
- Completed topics may be collapsed, listed below, or placed behind a simple `Completed` link.
- Cards show title, notes preview, scheduled time, and created-by metadata.
- Provide an obvious done action.

Empty state:

```text
Nothing to discuss later yet.
Save a topic now and come back to it at the right time.
```

## Quick add

The main page should offer:

- Title
- Optional date
- Optional time
- Optional notes through `Add details` or the full form

Requirements:

- Title stays immediately visible.
- Date/time may wrap on narrow screens.
- Default to no schedule; do not invent one.
- Support normal POST.
- HTMX is optional if it cleanly refreshes grouped sections.
- Preserve values and errors on failure.
- Do not request notification permission from this form.

## Topic detail/edit

Show:

- Title
- Notes
- Scheduled date/time or `No reminder scheduled`
- Pending/done state
- Created-by metadata
- Completion metadata
- Edit
- Mark Done / Mark Not Done
- Delete

Rules:

- Escape notes safely.
- Reuse existing safe URL rendering if available.
- Rescheduling resets reminder state.
- Marking done before the scheduled time prevents notification.
- Reopening an overdue processed topic does not resend until rescheduled.
- Use a delete confirmation page.
- Do not notify on done/undone changes.

## Existing Web Push integration

Reuse the existing `push_notifications` app, `PushSubscription`, VAPID settings, permission UI, `send_push_notification`, and service worker.

Do not create Firebase configuration, another subscription model, another service worker, another VAPID key pair, or another permission prompt.

Talk Later reminders differ from grocery activity notifications:

- Notify all current household members, including the creator.
- Send to every active device subscription.
- Do not use/suffer the grocery activity cooldown.
- Do not change Grocery Lists notification semantics.

Add a dedicated helper in `push_notifications.services`, for example:

```python
send_scheduled_reminder_to_household(*, household_id, payload)
```

Requirements:

- Reuse `send_push_notification`.
- Return simple attempted/successful counts or a small result object.
- Do not update the grocery cooldown/activity fields.
- Preserve existing expired-subscription cleanup.
- One device failure must not stop other deliveries.
- Do not log endpoints, keys, or notes.

## Push payload

At reminder time:

Title:

```text
Talk Later
```

Body:

```text
It's time to discuss: Holiday budget
```

Payload:

- `title`
- `body`
- `url`
- `tag`

Rules:

- Link to the topic page.
- Use tag `talk-later-<topic-id>`.
- Do not include notes.
- Do not expose internal IDs in visible text.
- Treat title as plain text.
- Use current service worker generic notification handling. Modify the service worker only if required for the route.

## Due processing

A topic is eligible when:

- `is_done=False`
- `scheduled_for` is not null
- `scheduled_for <= timezone.now()`
- `reminder_processed_at` is null
- `reminder_claimed_at` is null or stale

Implement `process_due_reminders`:

1. Claim eligible topics atomically.
2. Prevent concurrent scheduler calls from processing the same topic.
3. Use a reasonable batch limit, such as 100.
4. Avoid long database locks during external push calls.
5. After each attempt:
   - Set `reminder_processed_at`.
   - Set `reminder_sent_at` if at least one push succeeded.
6. Allow stale claims to retry.
7. Do not retry normally processed topics every minute.
8. Log only safe IDs/counts, never notes or subscription secrets.
9. Return counts for claimed, processed, sent, no-subscription, and failed topics.

Do not introduce Celery, Redis, Pub/Sub, Cloud Tasks, or a general job system.

## Management command

Add:

```bash
python manage.py process_talk_later_reminders
```

It should:

- Call the same processing service.
- Print concise counts.
- Accept optional `--limit`.
- Be useful for local/manual testing.
- Never duplicate already processed reminders.

Docker example:

```bash
docker compose exec web python manage.py process_talk_later_reminders
```

## Internal Cloud Scheduler endpoint

Add:

```text
POST /internal/talk-later/process-reminders/
```

Configuration:

```dotenv
TALK_LATER_REMINDER_JOB_TOKEN=replace-with-a-long-random-secret
```

Requirements:

- Read the token from settings.
- Require it in `X-Reminder-Token`.
- Compare with `secrets.compare_digest`.
- Return 403 for invalid/missing token.
- Require POST.
- Exempt only this endpoint from CSRF because it is not browser-driven.
- Do not put the token in a query string.
- Do not accept ordinary logged-in sessions as scheduler authorization.
- Call the same service as the management command.
- Return compact JSON counts.
- Never return topic content, subscriptions, secrets, or stack traces.
- Add safe logs.
- Put only a placeholder in `.env.example`.
- If push is disabled, return a safe no-op result.

## Cloud Scheduler README instructions

Exact-time reminders require server-side polling. Update README with owner steps:

1. Generate a secret:

```bash
openssl rand -hex 32
```

2. Store it as the Cloud Run environment variable:

```text
TALK_LATER_REMINDER_JOB_TOKEN
```

3. Deploy a new revision.
4. Create a Google Cloud Scheduler HTTP job:
   - Schedule: `* * * * *`
   - Time zone: `Europe/Amsterdam`
   - Method: `POST`
   - URL: `https://<cloud-run-url>/internal/talk-later/process-reminders/`
   - Header: `X-Reminder-Token: <same-secret>`
5. Use `Run now` and verify HTTP 200.
6. Schedule a test topic a few minutes ahead.
7. Verify all subscribed household devices receive one reminder.

Add a `gcloud` example with placeholders only if consistent with current docs. Do not include real project IDs, URLs, or tokens.

Warnings:

- Disabling Scheduler stops timed reminders.
- Notifications must be enabled separately on every device.
- The scheduler token and VAPID private key are different secrets.
- Regenerating VAPID keys requires devices to subscribe again.

Do not add Terraform solely for this feature.

## Local development

Add the placeholder token to `.env.example`.

Document:

1. Start Docker.
2. Enable notifications in test browsers/devices.
3. Create a topic one or two minutes ahead.
4. Run the management command.
5. Verify notification click opens the topic.
6. Run the command again and verify no duplicate.

Endpoint example:

```bash
curl -X POST   -H "X-Reminder-Token: replace-with-local-token"   http://127.0.0.1:8000/internal/talk-later/process-reminders/
```

## Admin

Register `DiscussionTopic`.

Show title, household, schedule, done state, creator/completer, reminder processed/sent timestamps, and created time. Add useful search, household/done/date filters, and safe ordering. Reminder-state timestamps should be read-only.

## Styling

Follow existing Home Sweet Home styling:

- Warm neutral background
- White cards
- Soft green accent
- Rounded corners
- Minimal shadows
- Mobile-first layout
- Large touch targets
- Accessible contrast
- Visible focus

Make overdue topics clear without relying on color only. Done topics should have a check mark and muted treatment. Do not redesign other modules. Test at 320px, 375px, tablet, and desktop.

## Tests

Add roughly 10–16 focused tests and mock real push delivery:

1. Authentication redirect.
2. Same-household access.
3. Cross-household denial.
4. Topic creation without schedule.
5. Clearly past new schedules rejected.
6. Done sets metadata and blocks eligibility.
7. Reopening preserves processed reminder state.
8. Rescheduling resets reminder fields.
9. Due processing ignores future, done, unscheduled, and processed topics.
10. Repeated/concurrent processing does not send twice.
11. Stale claims can retry.
12. All current household members, including creator, are recipients.
13. Outside-household users receive nothing.
14. Invalid scheduler token returns 403.
15. Valid scheduler request returns safe counts.
16. Push failure does not crash the batch.
17. Dashboard summary shows pending count and next reminder.

Reuse existing push test helpers. Do not make external push calls or add browser automation.

## README

Document:

- Talk Later overview
- Optional scheduling
- Done/not-done behavior
- Reminder behavior
- Per-device notification permissions
- Management-command testing
- Internal endpoint/token
- Cloud Scheduler setup
- Troubleshooting for disabled push, no subscriptions, denied permission, disabled scheduler, invalid token, and changed VAPID keys
- Migration/test commands

Preserve Grocery Lists, Household Chores, PWA, Web Push, Docker, CI/CD, Cloud Run, migration, and superuser docs.

## Out of scope

Do not implement a full calendar, calendar integrations, recurrence, multiple reminders, snooze, email/SMS, participant selection, comments, attachments, priorities, labels, natural-language date parsing, AI suggestions, voice input, location reminders, Firebase, Celery, Redis, Pub/Sub, Cloud Tasks, a general job framework, or a large test suite.

## Verification

Run the repository's normal workflow:

```bash
docker compose config
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
```

Manually verify dashboard/navigation, scheduled and unscheduled topics, time grouping, authorization, done/reopen/reschedule behavior, one-time processing, stale-claim behavior, scheduler-token security, delivery to all household devices including creator, exclusion of outsiders, notification click URL, and that Grocery Lists, Chores, PWA, and existing push notifications still work.

At the end, provide a concise summary of files, model/migration, routes, reminder processing, push changes, environment variables, Cloud Scheduler owner steps, tests, and assumptions.

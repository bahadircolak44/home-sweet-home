# Home Sweet Home — Household Chores Implementation Prompt

You are modifying the existing Django repository `bahadircolak44/home-sweet-home`.

Inspect the current implementation first. Work directly in the existing repository. Do not rebuild the project, create a nested project, duplicate existing household/PWA/push infrastructure, or replace working Grocery Lists functionality.

The project already has Django templates, PostgreSQL, household memberships, a dashboard, Grocery Lists, HTMX, PWA support, Web Push notifications, Docker, CI/CD, and Cloud deployment. The dashboard currently shows Household Chores as `Work in Progress`.

Everything added to the repository must be in English: source code, templates, labels, messages, comments, tests, migrations, admin text, and README documentation.

Do not commit or push changes.

## Goal

Activate the **Household Chores** module.

Household members must be able to:

- Create a chore session such as `This Week`, `Weekend Cleaning`, or `Before Guests Arrive`.
- Add custom tasks to a session.
- Assign each task to a member of the same household.
- Mark tasks done or not done.
- See tasks grouped by assigned member.
- Quickly add reusable common chores from a household-specific quick list.
- Complete a session and view it in history.

Keep the feature focused on sessions, tasks, assignment, and completion. Do not implement recurring schedules, due dates, calendars, points, rewards, or project-management features.

## Django app

Create an app named `chores` using the existing project conventions. A simple structure with `models.py`, `forms.py`, `services.py`, `views.py`, `urls.py`, `admin.py`, `tests.py`, migrations, and templates is enough.

Do not add a REST API, repository layer, frontend framework, or signals for normal application flow.

## Models

### ChoreSession

Fields:

- `household`: ForeignKey to `Household`
- `name`: CharField, maximum about 120 characters
- `notes`: TextField, blank
- `status`: Django `TextChoices` with `ACTIVE` and `COMPLETED`
- `created_by`: ForeignKey to user
- `completed_by`: nullable ForeignKey to user
- `created_at`
- `updated_at`
- `completed_at`: nullable DateTimeField

Rules:

- New sessions are active.
- Trim name and notes.
- Reject empty/whitespace-only names.
- Limit notes to about 1,000 characters through form validation.
- Active sessions order by most recently updated.
- Completed sessions order by newest completion time.
- Add useful household/status indexes.
- Completed sessions are read-only through all normal endpoints.
- Provide efficient total, done, remaining, and completion-percentage values without N+1 queries.

The create form may suggest an editable name such as `Week of 28 July 2026`. Do not automatically generate weekly sessions.

### ChoreTemplate

This is the reusable quick-list model.

Fields:

- `household`
- `title`
- `default_assignee`: nullable ForeignKey to user
- `is_active`: BooleanField, default `True`
- `created_by`
- `created_at`
- `updated_at`

Rules:

- Templates belong to one household only.
- Trim and validate title; maximum about 160 characters.
- A default assignee must be a current member of the same household.
- Inactive templates do not appear in Quick Add.
- Templates are definitions only. Existing tasks must not change when a template changes.
- Deleting/deactivating a template must not delete historical tasks.
- Do not seed personal chore data in migrations.

### ChoreTask

Fields:

- `session`: ForeignKey to `ChoreSession`
- `title`
- `assignee`: nullable ForeignKey to user
- `source_template`: nullable ForeignKey to `ChoreTemplate`, `SET_NULL`
- `is_done`: BooleanField, default `False`
- `created_by`
- `completed_by`: nullable ForeignKey to user
- `created_at`
- `updated_at`
- `completed_at`: nullable DateTimeField

Rules:

- Trim and validate title; maximum about 160 characters.
- Assignee must be a current member of the session household.
- Source template must belong to the same household.
- The same template may be added only once to the same session. Use a conditional database constraint where practical.
- Custom tasks may have duplicate titles.
- Unassigned tasks are allowed and appear under `Unassigned`.
- Marking done sets `completed_by` and `completed_at=timezone.now()`.
- Marking not done clears completion metadata.
- Any task create/edit/reassign/delete/toggle updates the parent session's `updated_at`.
- Tasks inside completed sessions are immutable, including crafted POST requests.

## Authorization

Reuse existing household membership and authorization patterns.

Every endpoint must ensure:

1. The user is authenticated.
2. The requested session/task/template belongs to the user's household.
3. Submitted assignees belong to that household.

Never trust IDs from URLs or forms. Filter querysets by household before `get_object_or_404`. Use POST and CSRF for state changes. Users without a household should receive the project's existing friendly behavior.

All household members have equal access in this MVP. Do not add roles.

## Services and transactions

Put meaningful state changes in `chores/services.py`. Use small functions such as:

- `create_session`
- `update_session`
- `delete_session`
- `complete_session`
- `create_task`
- `create_task_from_template`
- `update_task`
- `toggle_task`
- `delete_task`
- `create_template`
- `update_template`
- `deactivate_template`

Use `transaction.atomic` and `select_for_update` where useful. Add one clear domain exception such as `InvalidChoreOperation`.

Do not keep business rules only in views, templates, or JavaScript.

## Routes

Use namespace `chores`.

Suggested routes:

```text
/chores/
/chores/new/
/chores/<session-id>/
/chores/<session-id>/edit/
/chores/<session-id>/complete/
/chores/<session-id>/delete/
/chores/history/
/chores/history/<session-id>/

/chores/<session-id>/tasks/add/
/chores/<session-id>/quick-add/<template-id>/
/chores/tasks/<task-id>/edit/
/chores/tasks/<task-id>/toggle/
/chores/tasks/<task-id>/delete/

/chores/quick-list/
/chores/quick-list/new/
/chores/quick-list/<template-id>/edit/
/chores/quick-list/<template-id>/delete/
```

Use named URLs and `reverse`. Do not hard-code internal paths.

## Dashboard and navigation

Replace the disabled Household Chores card with an active card showing:

- Icon: `🧹`
- Title: `Household Chores`
- Description: `Assign and complete household tasks together.`
- Active-session count
- Remaining-task count
- Action: `Open Household Chores`

Make the whole card clickable and remove `Work in Progress`.

Add Chores to authenticated navigation. The modules should be:

- Home
- Grocery Lists
- Household Chores

Keep mobile navigation usable at 320px. A compact mobile label such as `Chores` is fine. Do not add Talk Later in this task.

## Session index

Create `/chores/`.

Show:

- `Household Chores`
- Household name
- `New Chore Session`
- Active session cards
- `Chore History`
- `Manage Quick List`

Each card shows name, optional notes preview, total/done/remaining counts, progress, and last update. The card is clickable.

Empty state:

```text
No active chore sessions yet.
Create a session for this week, a cleaning day, or any shared household plan.
```

## Session create/edit

The form contains only:

- Name
- Optional notes

Use Django forms and inline errors. Completed sessions cannot be edited. Do not add dates, recurrence, category, color, or owner fields.

## Session detail

Show:

- Back navigation
- Session name and optional notes
- Overall progress
- Compact custom-task form
- Quick Add panel
- Tasks grouped by assignee
- Edit, Complete Session, and Delete actions

Group tasks by household member, with an `Unassigned` group when needed. Use full name when available, otherwise username. Show per-person progress when it remains visually clean.

Example:

```text
Bahadir — 2 of 3 done
[✓] Take out the bins
[ ] Clean the kitchen

Pinar — 1 of 2 done
[✓] Water the plants
[ ] Clean the bathroom

Unassigned
[ ] Buy cleaning supplies
```

### Custom task form

Allow:

- Title
- Assignee selected from current household members
- `Unassigned`

Normal POST is required. HTMX may refresh task groups and progress if consistent with the existing app.

### Quick Add

Show active household templates. Each row has:

- Template title
- Default assignee or `Unassigned`
- `Add` button
- Clear already-added state

One tap creates an independent task using the current default assignee. Prevent adding the same template twice. Keep this as one-button rows; do not build a complex formset or multi-select table.

If empty:

```text
Create reusable chores to add common tasks with one tap.
```

Link to `Manage Quick List`.

## Task actions

Active-session tasks support:

- Toggle done/not done
- Edit title
- Change assignee
- Delete

Use large touch targets. HTMX is appropriate for toggles. Refresh grouping and progress after toggle/reassignment.

A household member may complete a task assigned to someone else; record the acting user in `completed_by`.

Done tasks should have a check mark and muted/line-through title. Completed-session tasks cannot be modified.

## Quick-list management

Create a simple page to create, edit, assign, activate/deactivate, and remove reusable templates.

Fields are only:

- Title
- Default assignee

Prefer deactivation when a template has been used. Never delete historical tasks. Do not add room, category, recurrence, duration, priority, or instructions.

## Completing sessions

Always show a confirmation page.

If tasks remain:

```text
This session still has 3 unfinished tasks.
```

Actions:

- `Return to Session`
- `Complete Anyway`

Completion sets status, `completed_by`, and `completed_at`, then redirects to history detail. Completed sessions are read-only. Do not implement reopen or clone.

## History

Create `/chores/history/`.

Cards show session name, completion date, task count, done count, and who completed it.

History detail shows session metadata and tasks grouped by assignee, including done/not-done state and completion metadata. It is read-only.

## Push notifications

The repository already has `push_notifications.services.schedule_household_notification`. Reuse it. Do not create another notification app, subscription model, permission flow, service worker, or VAPID setup.

Send only useful chore activity notifications:

- Task created or reassigned:
  `Bahadir assigned Clean the kitchen to Pinar.`
- Task completed:
  `Pinar completed Clean the kitchen.`
- Session completed:
  `Bahadir completed Weekend Cleaning.`

Requirements:

- Notify other household members, not the actor.
- Use existing transaction-on-commit behavior.
- Use a stable tag such as `chore-session-<id>`.
- Link to active session or history detail.
- Do not notify for template-management changes.
- Preserve current Grocery Lists notification behavior and cooldown policy.

## Admin

Register all three models with useful list columns, search, filters, and read-only timestamps.

Do not add complicated admin actions.

## Styling

Reuse existing CSS variables/components and visual identity:

- Warm neutral background
- White cards
- Soft green accent
- Rounded corners
- Minimal shadows
- Mobile-first layout
- Large touch targets
- Visible keyboard focus
- Accessible contrast

Do not redesign Grocery Lists or add Bootstrap, Tailwind, React, or external decorative images. Test around 320px, 375px, tablet, and desktop.

## Tests

Add a focused set of roughly 8–12 tests:

1. Authentication redirect.
2. Same-household access.
3. Cross-household session/task/template denial.
4. Assignee must belong to the household.
5. Custom task creation and assignment.
6. Quick template can be added once per session.
7. Toggle sets and clears completion metadata.
8. Task changes touch the parent session.
9. Completed sessions are read-only.
10. Active/completed sessions appear on correct pages.
11. Dashboard summary counts active sessions and remaining tasks.
12. Chore notifications reuse the existing push service and exclude the actor.

Mock real push delivery. Do not add browser automation or a large fixture framework.

## README

Update the English README with:

- Active Household Chores module
- Sessions
- Task assignment
- Done/not-done behavior
- Quick List
- History
- Chore notifications
- Migration and test commands

Preserve current Grocery Lists, PWA, Web Push, Docker, Cloud Run, CI/CD, migration, and superuser documentation.

## Out of scope

Do not implement recurring chores, automatic weekly sessions, due dates, reminders, calendar integration, priority, categories, rooms, duration, points, rewards, comments, attachments, subtasks, drag-and-drop, workload balancing, public sharing, a REST API, or Talk Later.

## Verification

Run the repository's current workflow, including:

```bash
docker compose config
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
```

Manually verify dashboard activation, summaries, session creation, household assignment options, authorization, custom add, quick add, duplicate prevention, grouping, progress, reassignment, completion confirmation, history, read-only behavior, existing Grocery Lists, PWA, and Push Notifications.

At the end, provide a concise summary of files, models, migration, routes, dashboard/navigation changes, notifications, tests, and assumptions.

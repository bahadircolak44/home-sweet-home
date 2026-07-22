# Home Sweet Home — Coding Agent Implementation Prompt

You are working inside an existing Git repository named:

```text
home-sweet-home
```

The repository has already been cloned, opened in VS Code, and a Python virtual environment has already been created.

Implement the application directly in the current repository.

Do not create another nested repository or an extra top-level directory such as:

```text
home-sweet-home/home-sweet-home/
```

The Django configuration package must be named:

```text
home_sweet_home
```

The user-facing application name must be:

```text
Home Sweet Home
```

Everything in the project must be written in English.

This includes:

- Source code
- Variable and function names
- Model names
- Comments
- Templates
- Page titles
- Button labels
- Validation messages
- Django Admin labels
- README documentation
- Test names
- Example data

Do not use Turkish text anywhere in the repository.

Do not commit or push changes. Implement the project, verify it locally, and leave the changes ready for review.

---

## 1. Product goal

Build the first MVP of a private household web application called **Home Sweet Home**.

The first module is a shared grocery-list application for two household members.

It replaces the use of a WhatsApp group for maintaining grocery lists.

Both household members must be able to:

- Sign in with their own account.
- Access the same household.
- See the same grocery lists.
- Create multiple active grocery lists.
- Add grocery items.
- Remove grocery items.
- Mark items as purchased.
- Return purchased items to the remaining-items section.
- Complete a grocery list.
- View completed grocery lists in history.

Keep the MVP intentionally small and focused.

Do not implement general household chores yet, but structure household membership so another Django app for chores can be added later.

---

## 2. Technical stack

Use:

- Python 3.13
- A current stable Django version compatible with Python 3.13
- Django templates
- Server-rendered HTML
- Django built-in authentication
- HTMX for a few small interactions
- Plain CSS
- PostgreSQL in every environment
- Psycopg 3
- `dj-database-url`
- `python-dotenv`
- WhiteNoise
- Gunicorn
- Docker
- Docker Compose

Do not use:

- React
- Vue
- Angular
- Django REST Framework
- Bootstrap
- Tailwind build tooling
- Node.js build tooling
- Celery
- Redis
- WebSockets
- A separate frontend project
- Terraform
- Kubernetes
- CI/CD configuration

HTMX may be loaded from a CDN.

All important actions must also work as normal HTML form submissions when HTMX is unavailable.

---

## 3. Environment strategy

The application must support different environments using environment variables and environment-specific Django settings.

Use a settings package instead of a single large `settings.py`.

Recommended structure:

```text
home_sweet_home/
├── settings/
│   ├── __init__.py
│   ├── base.py
│   ├── local.py
│   └── production.py
```

Requirements:

- `base.py` contains shared settings.
- `local.py` contains local development settings.
- `production.py` contains production-safe settings.
- Local development uses PostgreSQL from Docker Compose.
- Production uses PostgreSQL through `DATABASE_URL`.
- The selected settings module must be controlled with `DJANGO_SETTINGS_MODULE`.
- Do not hard-code database credentials.
- Do not use SQLite.
- Keep production settings compatible with a future hosted PostgreSQL provider such as Neon, Cloud SQL, or another standard PostgreSQL service.
- Changing environments should only require changing environment variables, not application code.

Default local value:

```dotenv
DJANGO_SETTINGS_MODULE=home_sweet_home.settings.local
```

Example production value:

```dotenv
DJANGO_SETTINGS_MODULE=home_sweet_home.settings.production
```

---

## 4. Initialize the Django project

Create the Django project in the current repository.

The resulting structure should be similar to:

```text
home-sweet-home/
├── manage.py
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── home_sweet_home/
│   ├── __init__.py
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py
│       ├── local.py
│       └── production.py
├── households/
│   ├── migrations/
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   └── services.py
├── shopping/
│   ├── migrations/
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
│   ├── services.py
│   ├── urls.py
│   ├── views.py
│   └── tests.py
├── templates/
│   ├── base.html
│   ├── errors/
│   │   ├── 403.html
│   │   ├── 404.html
│   │   └── 500.html
│   ├── registration/
│   │   └── login.html
│   └── shopping/
│       ├── active_lists.html
│       ├── list_detail.html
│       ├── list_form.html
│       ├── list_confirm_delete.html
│       ├── list_complete_confirmation.html
│       ├── history.html
│       ├── history_detail.html
│       └── partials/
│           ├── list_card.html
│           ├── item_sections.html
│           ├── item_row.html
│           └── progress.html
└── static/
    └── css/
        └── app.css
```

Small structural improvements are allowed, but keep the architecture simple.

Do not introduce unnecessary layers, repositories, interfaces, or abstractions.

---

## 5. Docker requirements

Create a production-capable but simple `Dockerfile`.

Requirements:

- Use an official slim Python 3.13 image.
- Set useful Python environment variables such as:
  - `PYTHONDONTWRITEBYTECODE=1`
  - `PYTHONUNBUFFERED=1`
- Install only the system packages required to build and run the project.
- Install Python dependencies from `requirements.txt`.
- Copy the application into the image.
- Use a non-root user where practical.
- Expose port `8000`.
- Use Gunicorn as the default container command.
- Keep the image simple and easy to understand.
- Do not create a complicated multi-stage image unless it meaningfully reduces complexity.

Create a `docker-entrypoint.sh`.

It should:

1. Stop immediately when a command fails.
2. Wait for PostgreSQL to become available.
3. Run migrations.
4. Run `collectstatic --noinput`.
5. Execute the container command.

The wait logic may use a small Python script or PostgreSQL readiness command. Avoid adding large dependencies only for this purpose.

---

## 6. Docker Compose requirements

Create `docker-compose.yml` with at least these services:

### `db`

Use PostgreSQL.

Recommended image:

```text
postgres:17-alpine
```

Requirements:

- Use environment variables for:
  - Database name
  - Database user
  - Database password
- Persist PostgreSQL data in a named volume.
- Add a health check using `pg_isready`.
- Do not expose PostgreSQL publicly beyond what is necessary for local development.
- Mapping port `5432:5432` is acceptable for convenient local database access.

### `web`

Requirements:

- Build from the local `Dockerfile`.
- Depend on a healthy database service.
- Load environment variables from `.env`.
- Use the local Django settings module.
- Bind port `8000:8000`.
- Mount the repository into the container for local development.
- Run Django development server for the local Compose workflow.
- Keep Gunicorn as the Dockerfile default for production-style execution.

The local Compose command may be:

```text
python manage.py runserver 0.0.0.0:8000
```

The application must be runnable with:

```bash
docker compose up --build
```

The application must then be available at:

```text
http://127.0.0.1:8000/
```

Use a named volume for PostgreSQL data.

Optionally use a named volume for static files only if it provides a real benefit.

Do not add services that are not needed.

---

## 7. Environment variables

Create `.env.example` with at least:

```dotenv
DEBUG=True
SECRET_KEY=replace-me
DJANGO_SETTINGS_MODULE=home_sweet_home.settings.local

ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

POSTGRES_DB=home_sweet_home
POSTGRES_USER=home_sweet_home
POSTGRES_PASSWORD=home_sweet_home
POSTGRES_HOST=db
POSTGRES_PORT=5432

DATABASE_URL=postgresql://home_sweet_home:home_sweet_home@db:5432/home_sweet_home
```

Requirements:

- `.env` must be ignored by Git.
- `.env.example` must contain only safe example values.
- `DATABASE_URL` is the source of truth for Django database configuration.
- The other PostgreSQL variables are used by Docker Compose and may also help construct the local URL.
- Production should work with any standard PostgreSQL connection string.
- Parse comma-separated hosts and origins safely.
- Do not include real credentials.

---

## 8. Authentication

Use Django's built-in user model.

Requirements:

- Only authenticated users may access the application.
- Unauthenticated visitors must be redirected to the login page.
- Do not implement public registration.
- Do not implement email verification.
- Do not implement password reset.
- Do not implement social login.
- Do not implement anonymous share links.
- Do not implement an invitation flow.

Users will initially be created through Django Admin.

Provide:

- A mobile-friendly login page.
- Username and password fields.
- Clear validation errors.
- A POST-based logout form.
- Redirect authenticated users to the active grocery-list page.

---

## 9. Household models

Create a Django app named:

```text
households
```

### Household

Fields:

- `name`
- `created_at`
- `updated_at`

Requirements:

- Use sensible maximum lengths.
- Add a useful `__str__` method.
- Register the model in Django Admin.

### HouseholdMembership

Fields:

- `household`
- `user`
- `joined_at`

Requirements:

- A user cannot have duplicate membership in the same household.
- Add a database-level unique constraint for:
  - `household`
  - `user`
- Add a useful `__str__` method.
- Register the model in Django Admin.
- Configure useful list columns and filters.

For this MVP, assume each user belongs to only one household.

Still implement access through household membership. Do not expose every grocery list to every authenticated user.

Create a small reusable service or helper that retrieves the current user's household.

If the user has no household membership:

- Do not crash.
- Display a friendly English message explaining that the account is not connected to a household.
- Do not expose internal exceptions.

---

## 10. Shopping models

Create a Django app named:

```text
shopping
```

### ShoppingList

Fields:

- `household`
- `name`
- `icon`
- `status`
- `created_by`
- `completed_by`
- `created_at`
- `updated_at`
- `completed_at`

Use Django `TextChoices` for `status`.

Supported values:

- `ACTIVE`
- `COMPLETED`

Requirements:

- A new list is always active.
- `completed_by` must be nullable.
- `completed_at` must be nullable.
- A completed list must be read-only in the normal application.
- The list must belong to exactly one household.
- Trim whitespace from the name.
- Reject empty or whitespace-only names.
- Use a reasonable maximum name length.
- Add useful indexes for household and status queries.
- Order active lists by most recently updated first.
- Order completed lists by completion time, newest first.

Provide properties or annotated values for:

- Total item count
- Purchased item count
- Remaining item count
- Completion percentage

Avoid N+1 query problems when rendering list cards.

Use annotations, `select_related`, or `prefetch_related` where appropriate.

### Icons

Do not implement image uploads.

Offer this fixed icon selection:

- 🛒
- 🇹🇷
- 🏠
- 🐈
- 🧴
- 📦

Default icon:

```text
🛒
```

### ShoppingItem

Fields:

- `shopping_list`
- `text`
- `is_purchased`
- `added_by`
- `purchased_by`
- `created_at`
- `updated_at`
- `purchased_at`

Requirements:

- Use one free-text field for the entire item description.
- Do not create separate fields for quantity, unit, category, brand, or price.
- Trim whitespace before validation or saving.
- Reject empty and whitespace-only values.
- Limit the text to 255 characters.
- `purchased_by` must be nullable.
- `purchased_at` must be nullable.

When an item is marked as purchased:

- Set `is_purchased` to `True`.
- Set `purchased_by` to the current user.
- Set `purchased_at` using `timezone.now()`.

When an item becomes unpurchased:

- Set `is_purchased` to `False`.
- Clear `purchased_by`.
- Clear `purchased_at`.

Whenever an item is added, deleted, or toggled:

- Update the parent shopping list's `updated_at`.

Ordering:

- Remaining items should use creation order.
- Purchased items should show the most recently purchased items first.

Register both shopping models in Django Admin.

Use useful:

- List columns
- Filters
- Search fields
- Read-only timestamps
- Related-object selectors

---

## 11. Authorization

Every shopping-related view must verify:

1. The user is authenticated.
2. The requested list belongs to a household in which the current user is a member.

Never trust list IDs or item IDs received from the browser.

Changing a URL manually must never expose or modify another household's data.

Create reusable authorized querysets or helper functions rather than repeating authorization code in every view.

All state-changing operations must use POST:

- Add item
- Toggle item
- Delete item
- Complete list
- Delete list
- Logout

Every form must use CSRF protection.

Completed lists must remain immutable even when someone manually sends a crafted POST request.

---

## 12. Required pages

### Active grocery lists

Suggested route:

```text
/
```

Show:

- Application name: `Home Sweet Home`
- Page title: `Grocery Lists`
- Current user's name or initials
- Active lists belonging to the user's household
- A `New List` button
- Navigation to history

Each active-list card must show:

- Icon
- List name
- Total number of items
- Purchased item count
- Remaining item count
- Progress bar
- Last updated time

The full card should be clickable.

When no active lists exist, show a friendly empty state and a clear:

```text
Create Your First List
```

action.

### Create and edit list

Allow users to:

- Enter a list name.
- Select an icon.
- Create the list.
- Edit the name and icon of an active list.

Requirements:

- Completed lists cannot be edited.
- Form errors must appear next to the relevant fields.
- Provide clear save and cancel actions.
- Use English labels and validation messages.

### Grocery-list detail

This is the main screen of the application.

It must be designed primarily for mobile use while shopping.

Show:

- Back button
- List icon
- List name
- Last-updated information
- Progress information
- Add-item form
- Remaining-items section
- Purchased-items section
- Edit-list action
- Complete-list action
- Delete-list action

#### Add-item form

Use:

- One text input
- One clear add button

Requirements:

- Position it near the top of the page.
- Pressing Enter should submit the form.
- Clear the input after a successful HTMX request.
- Keep or restore input focus when practical.
- Display validation errors without a full reload for HTMX requests.
- Support normal non-HTMX form submission.

Example placeholder:

```text
Add milk, bread, cat food...
```

#### Remaining-item rows

Each row must:

- Have a large mobile touch target.
- Allow toggling through the row or a clear checkbox-style control.
- Display the item text prominently.
- Display who added it in subtle secondary text.
- Include a delete action.
- Avoid requiring precise tapping on a small checkbox.

#### Purchased-item rows

Each row must:

- Display a visible check mark.
- Use muted styling.
- Use a line-through style.
- Display who purchased it when available.
- Allow returning it to the remaining section.
- Include a delete action.

When an item is added, deleted, or toggled through HTMX:

- Refresh both item sections.
- Refresh progress information.
- Preserve correct ordering.
- Do not depend on complicated client-side state.

Returning one combined partial containing the progress and both item sections is acceptable.

---

## 13. Completing a grocery list

Show a button labeled:

```text
Complete Shopping
```

If all items are purchased:

- Show a confirmation step.
- Complete the list after confirmation.

If one or more items remain:

- Show a confirmation page.
- Clearly display the number of remaining items.
- Offer:
  - `Return to List`
  - `Complete Anyway`

A list with zero items may also be completed, but it must require confirmation.

When completing:

- Use a transaction.
- Set status to completed.
- Set `completed_by`.
- Set `completed_at`.
- Redirect to the completed-list detail page.
- Show a success message.

After completion, normal application views must not allow:

- Adding items
- Deleting items
- Toggling items
- Renaming the list
- Changing the icon
- Deleting the list

---

## 14. History

### History page

Suggested route:

```text
/history/
```

Show completed lists ordered by completion time, newest first.

Each history card must display:

- Icon
- List name
- Completion date
- Total item count
- User who completed it

Provide a friendly empty state when no completed lists exist.

### History detail

Display:

- Icon
- List name
- Completion date and time
- User who completed the list
- All items
- User who added each item
- Purchased state
- User who purchased the item, when available

This page must be read-only.

Do not implement copying or reusing historical lists yet.

---

## 15. Delete-list flow

Allow deletion only for active lists.

Before deletion:

- Show a confirmation page.
- Clearly state that all items in the list will also be deleted.

Completed lists must not be deletable through the normal application interface.

---

## 16. HTMX usage

Use HTMX only for:

- Adding an item
- Toggling an item
- Deleting an item

Do not add HTMX to every screen.

Requirements:

- Handle CSRF correctly.
- Keep server-side validation.
- Use partial templates.
- Do not construct large HTML strings in Python.
- Return normal redirects for non-HTMX requests.
- Return appropriate HTTP status codes for invalid requests.
- Show a loading or disabled state when practical.
- Avoid optimistic updates that could disagree with server state.

---

## 17. Visual design

Create a polished, mobile-first design.

The application should feel like a warm household application, not a corporate dashboard.

Use:

- A very light cream or neutral background
- White cards
- A soft green primary accent
- Rounded corners
- Minimal shadows
- Large, readable typography
- Comfortable spacing
- Simple emoji icons
- Clear visual hierarchy

Requirements:

- Center content on larger screens.
- Use a reasonable desktop maximum width.
- Treat mobile as the primary layout.
- Support screen widths starting around 320px.
- Avoid horizontal scrolling.
- Use touch targets around 44px or larger.
- Keep the add-item input easy to reach.
- Make grocery-item rows easy to use with one hand.
- Use semantic HTML.
- Add accessible labels to icon-only buttons.
- Provide visible keyboard focus states.
- Do not communicate purchased state using color alone.
- Do not use decorative stock images.

Add mobile navigation for:

- `Lists`
- `History`

The navigation may be sticky or fixed, but it must not cover page content.

---

## 18. Messages and error handling

Use Django messages for events such as:

- List created
- List updated
- List deleted
- List completed
- Invalid operation
- Missing household membership

Display field-level form errors clearly.

Create custom English templates for:

- 403
- 404
- 500

Do not expose internal IDs, exceptions, environment values, or stack traces in production.

---

## 19. Django settings details

### Base settings

Include shared configuration for:

- Installed apps
- Middleware
- Templates
- Authentication redirects
- Static files
- WhiteNoise
- Database URL parsing
- Internationalization
- Default primary-key type
- Message framework
- Logging defaults

### Local settings

Use:

- `DEBUG=True`
- Local hosts
- Console email backend if email configuration is needed by Django
- PostgreSQL from Docker Compose
- Developer-friendly logging

### Production settings

Use:

- `DEBUG=False`
- Secure cookies
- Proxy SSL header support
- HTTPS redirect controlled by environment variables
- Strict allowed hosts
- Strict CSRF trusted origins
- Production database through `DATABASE_URL`
- WhiteNoise compressed static-file storage
- No hard-coded domains

Keep production settings simple and compatible with a future GCP deployment.

---

## 20. Requirements file

Create a minimal `requirements.txt`.

Include only dependencies actually required by this implementation, such as:

- Django
- psycopg
- dj-database-url
- python-dotenv
- whitenoise
- gunicorn

Pin versions to compatible, sensible versions.

Avoid unnecessary packages.

---

## 21. README

Create a concise but complete English `README.md`.

It must include the following sections.

### Project overview

Explain:

- What Home Sweet Home is.
- That the first module provides shared grocery lists.
- That public registration is intentionally excluded.
- That users and household memberships are initially managed through Django Admin.

### Technology stack

Briefly list:

- Django
- Django templates
- HTMX
- PostgreSQL
- Docker
- Docker Compose
- WhiteNoise

### Prerequisites

List:

- Docker
- Docker Compose
- Git
- Optional Python 3.13 for running management commands outside Docker

### Environment configuration

Include:

```bash
cp .env.example .env
```

Explain the main environment variables briefly.

### Start the application with Docker

Include:

```bash
docker compose up --build
```

Explain that the application is available at:

```text
http://127.0.0.1:8000/
```

### First migrations

This section is mandatory.

Include the Docker commands:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

Explain:

- `makemigrations` creates migration files based on model changes.
- `migrate` applies migrations to PostgreSQL.

Also explain that after cloning a repository that already contains migration files, the normal command is:

```bash
docker compose exec web python manage.py migrate
```

### Create a superuser

This section is mandatory.

Include:

```bash
docker compose exec web python manage.py createsuperuser
```

Explain that Django Admin is available at:

```text
http://127.0.0.1:8000/admin/
```

### Initial household setup

Document these exact steps:

1. Create a superuser.
2. Start the application.
3. Open Django Admin.
4. Create the second user under Users.
5. Create one household, for example `Home`.
6. Create two household memberships:
   - Superuser → Home
   - Second user → Home
7. Log into the main application using either account.

Explain that both users must belong to the same household to see the same grocery lists.

### Useful Docker commands

Include short explanations for:

```bash
docker compose up --build
docker compose up -d
docker compose down
docker compose down -v
docker compose logs -f web
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py shell
```

Explain clearly that:

```bash
docker compose down -v
```

deletes the local PostgreSQL volume and therefore removes local database data.

### Running management commands outside Docker

Optionally document that developers may activate the existing virtual environment and run:

```bash
pip install -r requirements.txt
python manage.py check
```

However, PostgreSQL must still be reachable and the environment variables must use the correct host.

Explain that:

- Inside Docker, the database host is `db`.
- From the host machine, the database host is usually `localhost`.

### Future production database

Explain that production can later use any standard PostgreSQL provider by replacing `DATABASE_URL`.

Example:

```dotenv
DJANGO_SETTINGS_MODULE=home_sweet_home.settings.production
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

Do not make Neon-specific configuration mandatory.

---

## 22. Simple tests

Add only a small, high-value test set.

Do not spend excessive time or tokens building a large test suite.

Use Django's built-in test framework.

Tests should cover only the most important behavior, approximately four to seven tests in total.

Prioritize:

1. An unauthenticated user is redirected to login.
2. Two users in the same household can access the same shopping list.
3. A user outside the household cannot access the list.
4. Adding an item records the current user.
5. Toggling an item sets and clears purchase metadata correctly.
6. Completing a list makes it read-only.
7. Completed lists appear in history.

It is acceptable to combine closely related assertions into the same test.

Do not add:

- Browser tests
- Selenium
- Playwright
- Snapshot tests
- Extensive CSS tests
- Large fixture files
- A complicated factory library
- Exhaustive tests for trivial Django behavior

Keep tests fast, readable, and focused on authorization and state transitions.

---

## 23. Implementation quality

Use:

- Named URL patterns
- Reverse URL resolution
- `timezone.now()`
- Database constraints
- Transactions for completion
- Reusable household authorization helpers
- `select_related`
- `prefetch_related`
- Query annotations when useful
- Small service functions for meaningful state changes
- Django forms for validation
- CSRF protection
- Semantic templates

Avoid:

- Signals for normal application flow
- Generic repository patterns
- Service classes with no meaningful purpose
- Event buses
- Abstract domain frameworks
- Premature support for many list types
- Stored item-count columns
- Duplicated authorization checks
- Business rules existing only in JavaScript
- Business rules existing only in templates
- Large comments explaining obvious code

---

## 24. Scope exclusions

Do not implement:

- Public registration
- Invitations
- Anonymous links
- Product categories
- Prices
- Budgets
- Receipts
- Images
- Barcode scanning
- Notifications
- Email
- Push messages
- Offline support
- Recipes
- AI features
- Maps
- Market locations
- Recurring household chores
- General task management
- Reusing old lists
- WebSockets
- Redis
- Celery
- Terraform
- Kubernetes
- CI/CD
- A large test suite

---

## 25. Acceptance criteria

The implementation is complete when:

1. The Django project runs from the current repository root.
2. The Django package is named `home_sweet_home`.
3. All visible text and documentation are in English.
4. Docker Compose starts both PostgreSQL and the Django application.
5. The application becomes available at `http://127.0.0.1:8000/`.
6. PostgreSQL data persists between ordinary container restarts.
7. An unauthenticated visitor is redirected to login.
8. Two members of the same household see the same active lists.
9. Multiple active grocery lists can be created.
10. Active-list names and icons can be edited.
11. Either member can add items.
12. Each item records who added it.
13. Either member can mark an item as purchased.
14. Purchase metadata is recorded correctly.
15. Purchased items appear in a separate section.
16. Purchased items can be returned to the remaining section.
17. Items can be deleted.
18. Progress information updates correctly.
19. Users cannot access lists belonging to another household.
20. Completing a list records the user and timestamp.
21. Lists with remaining items require explicit confirmation.
22. Completed lists disappear from active lists.
23. Completed lists appear in history.
24. Completed lists are read-only.
25. Active lists can be deleted after confirmation.
26. The main flow is usable on a narrow phone screen.
27. The application works with local Docker PostgreSQL.
28. Production database configuration works by replacing `DATABASE_URL`.
29. Initial migration files are created and ready to commit.
30. The README contains Docker, migration, superuser, and initial household setup instructions.
31. A small, focused test suite passes.

---

## 26. Verification

After implementation, run:

```bash
docker compose config
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
```

Also verify:

- The `db` service becomes healthy.
- The `web` service starts successfully.
- Static CSS loads.
- Login works.
- Logout works.
- The admin site works.
- Both household members see shared lists.
- Another household cannot access those lists.
- Item add, toggle, and delete work with HTMX.
- The same operations work without HTMX.
- Completing a list makes it immutable.
- Completed lists appear in history.
- Restarting the containers does not delete PostgreSQL data.
- No secrets are committed.
- No Turkish text exists in the repository.
- No unused imports, dead code, or placeholder comments remain.

At the end, provide a concise summary containing:

- Main files created
- Django apps and models added
- Available routes
- Docker services
- Environment variables
- Commands required to start the application
- Test result
- Any small assumptions made

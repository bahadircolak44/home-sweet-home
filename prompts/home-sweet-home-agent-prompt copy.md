````markdown
You are working on an existing Django project named **Home Sweet Home**.

The current application already supports:

- Authentication
- Households and household memberships
- Multiple active grocery lists
- Adding, purchasing, unpurchasing, and deleting grocery items
- Completing grocery lists
- Grocery-list history
- Django templates
- HTMX interactions
- PostgreSQL
- Docker and Docker Compose
- Mobile-responsive styling

Modify the existing implementation. Do not rebuild the project from scratch and do not replace working functionality unnecessarily.

Everything must remain in English:

- Source code
- Model and field names
- Templates
- Button labels
- Validation messages
- Admin labels
- Tests
- Documentation

Do not commit or push changes.

# Goal

Extend the application with:

1. Grocery-item quantity
2. Optional item description or product link
3. A proper application home dashboard
4. Grocery Lists as an application module
5. A disabled Household Chores preview
6. Progressive Web App support
7. Home-screen installation support

Keep the implementation simple and consistent with the existing design.

---

# 1. Grocery item quantity

Add a quantity field to `ShoppingItem`.

Recommended field:

```python
quantity = models.PositiveIntegerField(default=1)
````

Requirements:

* Quantity is required.
* Default quantity is `1`.
* Minimum value is `1`.
* Reject zero and negative values.
* Use Django form validation.
* Add the field through a normal Django migration.
* Existing grocery items must receive quantity `1`.
* Display quantity clearly in active and completed grocery lists.

Examples:

```text
2 × Milk
1 × Cat food
6 × Sparkling water
```

Avoid showing an unnecessarily prominent `1 ×` when that makes the interface visually noisy.

A suitable display rule is:

* For quantity `1`, show only the item name.
* For quantity greater than `1`, show a small quantity badge such as `2×`.

The quantity badge should remain visible for both remaining and purchased items.

---

# 2. Grocery item description

Add an optional description field to `ShoppingItem`.

Recommended field:

```python
description = models.TextField(blank=True)
```

Requirements:

* Description is optional.
* Trim leading and trailing whitespace.
* Do not store whitespace-only descriptions.
* Use a reasonable form limit, such as 1,000 characters.
* Do not add a separate product URL field.
* Users may enter:

  * A note
  * Product details
  * A preferred brand
  * A product URL
  * A combination of text and URLs

Examples:

```text
Prefer the 2 kg package.
Buy the low-salt version.
https://example.com/products/cat-food
The green package from the refrigerated section.
```

When rendered:

* Display the description beneath the item name.
* Use smaller and visually muted text.
* Do not reserve empty space when no description exists.
* Preserve line breaks where practical.
* Automatically convert valid URLs into clickable links.
* Open external links in a new tab.
* Add safe link attributes such as:

```html
target="_blank"
rel="noopener noreferrer"
```

Do not render user-entered HTML.

Use Django escaping and safe URL conversion. Do not use `safe` directly on user input.

---

# 3. Add-item form

Update the existing add-item interface.

The main item input should remain immediately visible.

Add:

* Item name
* Quantity
* Optional description

Recommended mobile-first structure:

```text
[ Add an item...                 ] [ Qty: 1 ] [ Add ]

+ Add details
```

When `Add details` is selected, reveal:

```text
[ Description or product link...                    ]
```

Requirements:

* Keep the form compact by default.
* Description should initially be collapsed.
* Use a small amount of plain JavaScript for expanding and collapsing the optional field.
* Do not introduce a frontend framework.
* The expanded state does not need to persist after navigation.
* Pressing Enter in the item-name input should submit the form.
* After a successful HTMX submission:

  * Clear the item name.
  * Reset quantity to `1`.
  * Clear the description.
  * Collapse the optional description field.
  * Restore focus to the item-name input when practical.
* Validation errors must work for both HTMX and normal requests.
* Preserve entered values when validation fails.

Keep the form easy to use on narrow mobile screens.

On very small screens, quantity and the add button may wrap onto a second row rather than causing horizontal scrolling.

---

# 4. Item display

Update remaining and purchased item rows.

Each item should support the following layout:

```text
[checkbox]  [2×] Cat food
                 Prefer the 2 kg package.
                 https://example.com/product
                 Added by Bahadir
```

Requirements:

* Item name remains the primary visual element.
* Quantity is clearly visible but compact.
* Description appears beneath the item name.
* Metadata such as `Added by` remains visually secondary.
* URLs inside descriptions are clickable.
* Purchased items must retain:

  * Quantity
  * Description
  * Link functionality
* Purchased styling should still include:

  * Check mark
  * Muted appearance
  * Line-through item name
* Do not apply line-through to URLs if that makes them difficult to read.
* Maintain touch targets of approximately 44px or larger.

Update completed-list history pages to show quantity and description as well.

---

# 5. Edit existing grocery items

Add a small and simple way to correct an existing item.

Users must be able to edit the following fields while a list is active:

* Item name
* Quantity
* Description

Requirements:

* Add an accessible `Edit` action to each active item.
* A simple dedicated edit page is acceptable and preferred over a complicated modal.
* Use a Django form.
* Completed-list items remain read-only.
* Editing an item must update the parent grocery list's `updated_at`.
* Protect the view using the existing household authorization rules.
* Use POST for saving changes.
* Display validation errors clearly.
* Return to the grocery-list detail page after a successful update.

Do not add inline JavaScript editing unless it is clearly simpler than a normal Django page.

---

# 6. Application dashboard

The root route `/` must become the main **Home Sweet Home dashboard**.

The root page must no longer directly display grocery lists.

Create a dashboard that introduces the available household modules.

Suggested layout:

```text
Home Sweet Home

Everything your household needs, in one place.

[ Grocery Lists ]
Shared grocery lists for everyone at home.
Open Grocery Lists

[ Household Chores ]
Shared household tasks and recurring chores.
Work in Progress
```

Requirements:

* The page title should be `Home`.
* The dashboard should match the existing warm, mobile-first design.
* Show the household name when available.
* Display module cards.
* Make the Grocery Lists card fully clickable.
* The Grocery Lists card should display a useful summary, such as:

  * Number of active lists
  * Total remaining grocery items
* Avoid unnecessary extra database queries.

The dashboard should be useful even with only one active module.

---

# 7. Grocery Lists module

Move the existing grocery-list index away from the root route.

Use a clear URL namespace such as:

```text
/groceries/
```

Suggested routes:

```text
/
/groceries/
/groceries/new/
/groceries/<list-id>/
/groceries/<list-id>/edit/
/groceries/<list-id>/complete/
/groceries/<list-id>/delete/
/groceries/history/
/groceries/history/<list-id>/
```

Exact URL naming may follow the existing project conventions, but:

* `/` must be the dashboard.
* Grocery Lists must be a distinct application module.
* Existing links and redirects must be updated.
* Use named URLs and `reverse`.
* Do not hard-code internal URLs in templates or Python code.

Update login redirects so authenticated users arrive at the main dashboard.

---

# 8. Household Chores preview

Add a second dashboard module card named:

```text
Household Chores
```

This feature is not implemented yet.

Requirements:

* Use a suitable simple icon, such as:

  * 🧹
  * 🛠️
  * 🚧
* Display an English status label:

  * `Work in Progress`
* Include a short English description such as:

```text
Shared household tasks and recurring chores.
```

* The card must look intentionally unavailable.
* Do not create chore database models.
* Do not create a chores Django app.
* Do not create fake forms or non-working pages.
* It may be a disabled card without a link.
* Use `aria-disabled="true"` where appropriate.
* Do not make users click into a dead-end page.

This card exists only to communicate the future direction of the application.

---

# 9. Navigation

Update global navigation to support multiple modules.

Recommended navigation:

* Home
* Grocery Lists

Inside the Grocery Lists module, provide access to:

* Active Lists
* History

On mobile, a suitable bottom navigation is:

```text
Home | Grocery Lists
```

History may remain a secondary navigation item within the Grocery Lists pages.

Requirements:

* Clearly indicate the currently active page or module.
* Navigation must not cover page content.
* Keep logout accessible from the user/profile area.
* Do not add a clickable Household Chores navigation item until that module exists.
* Maintain keyboard accessibility and visible focus states.

---

# 10. Progressive Web App support

Add basic Progressive Web App support so users can add **Home Sweet Home** to a phone's home screen.

Create:

```text
static/manifest.webmanifest
```

The manifest should contain values similar to:

```json
{
  "name": "Home Sweet Home",
  "short_name": "Home",
  "description": "Shared household lists and tools.",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#f7f5ef",
  "theme_color": "#6f8f72"
}
```

Use colors that match the existing design rather than blindly copying the example values.

Add application icons:

* 192×192 PNG
* 512×512 PNG
* 180×180 Apple touch icon
* A standard favicon

Requirements:

* Create simple original icons for the project.
* Use a simple house-based or house-and-checkmark design.
* Do not download copyrighted logos or stock artwork.
* The icon should remain recognizable at small sizes.
* Store icons under an appropriate static directory.
* Reference all icons correctly from the manifest and HTML.

Add to the base template:

* Manifest link
* Theme color
* Apple touch icon
* Mobile web-app meta tags
* Appropriate favicon references

The application must open in standalone mode after installation where supported.

---

# 11. Service worker

Add a minimal service worker.

Requirements:

* Register it from the base template or a small dedicated JavaScript file.
* Serve the service worker from a scope that can control the application.
* Keep the implementation intentionally conservative.
* Cache only safe static application assets such as:

  * CSS
  * Local JavaScript
  * Application icons
* Do not cache authenticated HTML pages.
* Do not cache form responses.
* Do not cache HTMX mutation responses.
* Do not attempt full offline grocery-list functionality.
* Do not risk showing one household member stale data.
* Network requests for application data must remain network-first or uncached.
* Service-worker failures must not break the application.
* Use a cache version so future deployments can invalidate old static assets.
* Remove old application caches during activation.

The purpose of the service worker in this iteration is lightweight PWA support, not offline data synchronization.

---

# 12. Install application experience

Add a small installation option to the dashboard.

Where supported, show a button such as:

```text
Install App
```

Requirements:

* Use the browser's `beforeinstallprompt` event where available.
* Hide the install button when installation is not supported or the application is already installed.
* Do not show a broken button.
* Use only a small amount of plain JavaScript.
* After successful installation, hide the button.

For iPhone and iPad Safari, the browser does not expose the same automatic installation prompt.

Provide a small help action such as:

```text
How to install
```

When selected on iOS, show concise instructions:

```text
Open the Share menu and select “Add to Home Screen”.
```

Do not display iOS instructions permanently to every user.

Keep the installation UI subtle. It must not dominate the dashboard.

---

# 13. HTTPS and local development

PWA functionality must be compatible with HTTPS production deployment.

Document that:

* Installation features require HTTPS in production.
* `localhost` is accepted for local development by supported browsers.
* Docker local development may still run over HTTP.
* Production will later be deployed behind HTTPS.

Do not add certificate generation or a local HTTPS proxy in this task.

---

# 14. Database migrations

Create and commit-ready migrations for:

* `ShoppingItem.quantity`
* `ShoppingItem.description`

Requirements:

* Existing items must receive quantity `1`.
* Existing items must receive an empty description.
* Do not delete or recreate current database tables.
* Do not squash existing migrations.
* Do not modify old migration files unless absolutely necessary.
* Generate a new migration following the existing migration history.

Run:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

If the current development setup uses a different valid Docker command, follow the repository's existing documented workflow.

---

# 15. Django Admin

Update the ShoppingItem admin configuration.

Display useful fields such as:

* Item text
* Quantity
* Shopping list
* Purchased status
* Added by
* Purchased by
* Created time

Add:

* Search by item text and description
* Purchased-state filter
* Shopping-list filter
* Read-only timestamp fields

Do not make the admin overly complex.

---

# 16. Tests

Add only a few focused tests for the new behavior.

Do not create a large test suite.

Add or update tests for:

1. Quantity defaults to `1`.
2. Quantity cannot be zero or negative through the application form.
3. Description is saved and displayed safely.
4. An item can be edited while its list is active.
5. An item cannot be edited after the list is completed.
6. The root route renders the dashboard.
7. The grocery-list index is available under its new module route.

Where practical, extend existing tests rather than duplicating setup.

Do not add browser automation, Selenium, Playwright, or snapshot testing.

PWA files may be checked with one simple response/static-file test if straightforward, but do not spend significant effort testing browser installation behavior.

---

# 17. README updates

Update the existing English README.

Document:

* The new dashboard.
* Grocery Lists as the first application module.
* Household Chores as a future module.
* Grocery-item quantity and description.
* Product links inside descriptions.
* PWA/home-screen installation support.
* The fact that full offline functionality is not implemented.

Add a concise section:

## Install on a phone

Include:

### Android

```text
Open the application in Chrome and choose Install App or Add to Home screen.
```

### iPhone and iPad

```text
Open the application in Safari, open the Share menu, and select Add to Home Screen.
```

Mention that production installation requires HTTPS.

Keep all existing Docker, migration, and superuser documentation intact.

Do not remove the existing required commands:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

---

# 18. Design consistency

Preserve the existing visual identity.

Do not redesign the whole application.

Improve the current design only where needed for:

* Dashboard module cards
* Quantity badge
* Description text
* Product links
* Install button
* Household Chores disabled state
* Updated navigation

Requirements:

* Mobile-first
* Warm household appearance
* Existing soft-green theme
* White cards
* Rounded corners
* Minimal shadows
* Large touch targets
* No horizontal overflow
* No external decorative imagery
* Good desktop spacing
* Accessible contrast
* Visible focus styles

The Household Chores card must look intentionally inactive without becoming unreadable.

---

# 19. Scope exclusions

Do not implement:

* Actual household chores
* Recurring tasks
* Notifications
* Offline form submission
* Background synchronization
* Push notifications
* Product previews from URLs
* URL metadata scraping
* Product images
* Prices
* Categories
* Barcode scanning
* Shopping-list sharing links
* New authentication mechanisms
* React or another frontend framework
* A large test suite

---

# 20. Verification

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

Manually verify:

1. `/` displays the new dashboard.
2. Grocery Lists is accessible as a module.
3. Existing grocery lists still work.
4. New items default to quantity `1`.
5. Quantities greater than `1` display clearly.
6. Descriptions are optional.
7. Product URLs are clickable and safely escaped.
8. Items can be edited in active lists.
9. Completed items and history retain quantity and description.
10. Completed-list items cannot be edited.
11. Household Chores appears as `Work in Progress`.
12. The manifest loads successfully.
13. PWA icons load successfully.
14. The service worker registers without console errors.
15. Authenticated HTML is not served from a stale cache.
16. The install button only appears when supported.
17. The layout works at approximately 320px, 375px, and desktop widths.
18. No Turkish text has been introduced.
19. Existing household authorization still works.
20. No secrets have been committed.

At the end, provide a concise summary containing:

* Models and fields changed
* Migration created
* Routes changed
* Templates changed
* PWA files added
* Tests added or updated
* Verification commands and results
* Any small assumptions made

```
```

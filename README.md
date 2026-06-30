# Digital Business Card (Odoo 19 module)

A native **Odoo** module for shareable **digital business cards** — the "link in
bio" / digital card idea popularised by [LinkStack](https://github.com/LinkStackOrg/LinkStack).

LinkStack itself is a PHP/Laravel app and **cannot** be dropped into Odoo (Odoo
is Python). This module re-implements the concept natively in Python + XML +
QWeb, and adds two integrations LinkStack doesn't have out of the box:

1. **Import** people (stored as HTML) from an external database **or** an HTTP API.
2. **Publish** selected cards to a **3rd-party web host**.

Every card gets a **permanent public link** (`/card/<slug>`) and an
**auto-generated QR code** that points at that link.

---

## Table of contents

- [What you get](#what-you-get)
- [Installation](#installation)
- [Quick start](#quick-start)
- [How the module works](#how-the-module-works)
- [Linking to Employees (HR)](#linking-to-employees-hr)
- [Connecting to a database (importing cards)](#connecting-to-a-database-importing-cards)
- [FAQ](#faq)

---

## What you get

| Capability | Where |
|---|---|
| A card per person (name, title, company, email, phone, website, bio, photo) | **Business Cards → Cards** |
| Link a card to an **HR employee** — details pulled live | card's **Employee** field / **Employees → Actions → Create Business Card** |
| Permanent public page per card | `http://<your-odoo>/card/<slug>` |
| Auto-generated QR code (points at the public page) | shown on the card form & public page |
| Import people from an external **PostgreSQL** DB or **HTTP** endpoint | **Business Cards → Data Sources** *(admin)* |
| Publish selected cards to a 3rd-party host | **Cards list → Actions ▾ → Publish to Web** |
| Define where to publish | **Business Cards → Publish Targets** *(admin)* |

---

## Installation

The module lives in `addons/` which is mounted into the Odoo container at
`/mnt/extra-addons` (see the repo's `docker-compose.yml`).

```bash
# from the project root that holds docker-compose.yml
docker compose up -d

# install into your database (replace 'learn' with your db name)
docker compose run --rm odoo odoo -d learn -i digital_business_card --stop-after-init
docker compose restart odoo
```

Then open **Apps → Business Cards**. To upgrade after code changes, swap `-i`
for `-u`:

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d learn -u digital_business_card --stop-after-init
docker compose start odoo
```

**Requirements:** Odoo 19, depends on `base`, `web` and `hr` (the Employees
app — installed automatically). QR generation uses
Odoo's built-in barcode engine; PostgreSQL import uses `psycopg2` and HTTP uses
`requests` — both already ship with Odoo, so there is nothing extra to install.

---

## Quick start

1. **Business Cards → Cards → New.**
2. Fill in the name and a **Card Link** (the `slug`, e.g. `jane`). The slug must
   be unique — it becomes the permanent URL.
3. Add a title, company, contact details, photo and bio. Save.
4. Open `http://<your-odoo>/card/jane` (or scan the QR shown on the form).

---

## How the module works

```
                ┌────────────────────────┐
  external DB ─▶│   Data Source (import)  │─┐
  / HTTP API    └────────────────────────┘ │   creates / updates
                                            ▼
                       ┌───────────────────────────────┐
                       │  digital.business.card (model) │
                       │  name, slug, contact, photo,   │
                       │  bio, source_html              │
                       │  → public_url, qr_code (computed)
                       └───────────────────────────────┘
                                            │
        public page  /card/<slug>  ◀────────┤ rendered by QWeb (auth: public)
                                            │
                       ┌───────────────────────────────┐
   3rd-party host  ◀───│  Publish Target (export)       │  Actions ▾ → Publish
                       └───────────────────────────────┘
```

- **`digital.business.card`** — one record per person. The `slug` field is the
  permanent handle; the public page is served at `/card/<slug>`.
- **`public_url`** is computed from the system `web.base.url` + slug.
- **`qr_code`** is computed (not stored) and always encodes `public_url`, so the
  QR can never drift out of sync with the link.
- **`source_html`** is an optional HTML body. When set, the public page renders
  it instead of the built-in layout. It is **sanitized** (scripts removed).
- The public page (`/card/<slug>`) is **public** (no login). It reads the card
  with `sudo()`, so record-level access rules don't block anonymous visitors.

### The fixed link vs the QR code

Like LinkStack, each card has **both**:

- a **fixed, permanent link** — `/<your-odoo>/card/<slug>`, and
- a **QR code** that is generated on demand and simply encodes that link.

The link never changes (as long as the slug stays the same); the QR image is
re-rendered each time it's displayed.

---

## Linking to Employees (HR)

Most companies already keep people in Odoo's **Employees** app, so a card can be
linked to an `hr.employee` and **display its details live** — while outsiders
only ever see the public card page, never the Employees app.

**Create cards from employees:** go to **Employees**, tick the people you want,
then **Actions ▾ → Create Business Card**. One card is made per employee (slug
auto-generated from the name; existing cards are reused, not duplicated), and the
created cards open so you can review them.

**Or link manually:** on any card, set the **Employee** field.

When a card is linked to an employee, the shown values come from the employee
and update automatically:

| Card shows | Pulled from `hr.employee` |
|---|---|
| Name | `name` |
| Title | `job_title` (falls back to `job_id`) |
| Company | `company_id` |
| Email | `work_email` |
| Phone | `work_phone` (falls back to `mobile_phone`) |
| Photo | `image_1920` |
| Website | the employee's company website |

If **no** employee is linked, the card uses its own manually-entered fields
instead. The employee is read internally with elevated rights, so a public
visitor with no HR access still sees the published contact details — that's the
whole point: **outsiders see the contact card, not the employee record.**

---

## Connecting to a database (importing cards)

> **Do you have to connect to the database?** Yes. To read people from another
> server, Odoo must open a connection to it — you supply the connection details
> once, and the module does the rest. This screen is **admin-only** because it
> stores credentials.

Go to **Business Cards → Data Sources → New**. Pick a **Source Type**.

### Option A — SQL database (PostgreSQL)

Fill in:

| Field | Example | Meaning |
|---|---|---|
| Host | `db` or `203.0.113.10` | DB server hostname/IP |
| Port | `5432` | PostgreSQL port |
| Database | `linkstack` | database name |
| Username / Password | `reader` / `••••` | credentials (read access is enough) |
| Table | `people` | table with one person per row |
| Key/Slug Column | `handle` | becomes the card's unique slug |
| HTML Column | `body` | the person's HTML |
| Name Column *(optional)* | `fullname` | display name (falls back to the slug) |
| Max Rows | `100` | safety limit per import |

Then:

1. Click **Test Connection** — confirms Odoo can reach the server.
2. Click **Import Cards** — reads the rows and **creates or updates** a card per
   row (matched by slug, so re-importing refreshes existing cards).

The SQL session is forced **read-only**, so an import can never modify the
source database.

### Option B — HTTP / URL

Fill in **URL** (and optionally an **Auth Token**, sent as
`Authorization: Bearer <token>`). The fetcher behaves like this:

- If the response is a **JSON array** (or `{ "data": [ ... ] }`) of objects, each
  object becomes a card. Recognised keys: `slug`/`id`/`username`, `name`,
  `html`/`content`.
- Otherwise the **whole response body** is treated as one person's HTML, and the
  slug is taken from the last path segment of the URL.

Buttons are the same: **Test Connection**, then **Import Cards**.

> By default the HTTP fetcher refuses private/internal addresses (SSRF guard).
> If your source is on a trusted internal network, tick **Allow internal
> addresses**.

---


### Models

| Model | File | Purpose |
|---|---|---|
| `digital.business.card` | `models/business_card.py` | the card; public link + QR |
| `digital.business.card.source` | `models/business_card_source.py` | import config (SQL/HTTP) |
| `digital.business.card.target` | `models/business_card_target.py` | publish config |
| `digital.business.card.publish.wizard` | `models/business_card_target.py` | "Publish to Web" dialog |
| *(helpers)* | `models/net_utils.py` | shared SSRF guard + size cap |

### Key methods

| Method | Model | What it does |
|---|---|---|
| `_compute_public_url` / `_compute_qr_code` / `_compute_website_url` | card | derive link, QR, safe URL |
| `_compute_contact` | card | the live `contact_*` values (employee when linked, else manual) |
| `create_for_employees(employees)` | card | make one card per employee (used by the Employees action) |
| `create_card_from_html_file(file_path, vals)` | card | **dormant** — build a card from a local HTML file; not wired to any button/route (parked for later) |
| `action_test_connection` / `action_import_cards` | source | buttons: test / import |
| `_fetch_rows_sql` / `_fetch_rows_http` / `_upsert_cards` | source | fetch + upsert by slug |
| `_publish_cards(cards)` | target | POST/PUT each card to the host |
| `action_publish` | wizard | publish the ticked cards |
| `assert_url_allowed(url, allow_private)` | net_utils | SSRF guard |

### Public route

| Route | Auth | Controller |
|---|---|---|
| `GET /card/<slug>` | public | `controllers/main.py` → `card_page` |

---

## FAQ

**Can it generate a QR code, or is the link fixed?** Both — the link is fixed
(`/card/<slug>`) and the QR is generated automatically and encodes that link.

**Does importing modify my source database?** No. The PostgreSQL connection is
read-only.

**Can normal users publish or configure sources?** No. Those screens are
admin-only. Normal users can manage their own cards.

**What about the `create_card_from_html_file` function?** It exists but is
intentionally dormant (not called anywhere). It's a starting point if you later
want to build cards from local HTML files.

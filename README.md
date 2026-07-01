# Digital Business Card (Odoo 17 module)

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

**Requirements:** Odoo 17, depends on `base`, `web` and `hr` (the Employees
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

**Each card has its own link and QR**, ready to share, print, or **write to an
NFC tag / business card**. Opening it shows only the standalone public card
page — visitors never reach the Odoo backend or any logged-in area from it.

The public page has an **Import to contact** button that downloads the person as
a **vCard (.vcf)**, so a viewer can save it straight into their phone contacts
(available at `/card/<slug>/vcard`).

---

## Linking to Employees (HR)

Most companies already keep people in Odoo's **Employees** app, so a card can be
linked to an `hr.employee` and **display its details live** — while outsiders
only ever see the public card page, never the Employees app.

**Every employee appears in the Cards list by name.** Until you generate a card
for them, the row shows the **name only** — no link, no QR, and the other
details are hidden. Generating is what creates the link + QR (and reveals the
details):

- In **Business Cards → Cards**, tick the name-only rows and click
  **Actions ▾ → Generate**, or open a card and click **Generate Link & QR**.
- From the Employees app: tick people → **Actions ▾ → Create Business Card**
  (creates + generates in one step).

**Automatic mode** (optional): **Business Cards → Card Generation** *(admin)* →
turn on **Automatically generate employee cards** and choose the scope (future
employees only, or all existing now). Then new employees get their link + QR
right away instead of staying name-only.

Slugs are generated from the name; existing cards are reused, never duplicated.

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

**Editable per card:** every field (position/title, email, phone, company,
website, photo) can be edited on the card. A value entered there **overrides**
the employee's; leave it blank to use the employee's live value. If **no**
employee is linked, the card simply uses its own fields.

The employee is read internally with elevated rights, so a public visitor with
no HR access still sees the published contact details — that's the whole point:
**outsiders see the contact card, not the employee record.**

---

## Connecting to a database (importing cards)

Import people from an external **PostgreSQL** database. Go to
**Business Cards → Data Sources → New** *(admin)* and fill in:

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
| Max Rows | `100` | how many rows to read per import |

Then:

1. Click **Test Connection** — confirms Odoo can reach the database.
2. Click **Import Cards** — reads the rows and **creates or updates** a card per
   row (matched by slug, so re-importing refreshes existing cards).

---


### Models

| Model | File | Purpose |
|---|---|---|
| `digital.business.card` | `models/business_card.py` | the card; public link + QR |
| `digital.business.card.source` | `models/business_card_source.py` | PostgreSQL import config |
| `digital.business.card.target` | `models/business_card_target.py` | publish config |
| `digital.business.card.publish.wizard` | `models/business_card_target.py` | "Publish to Web" dialog |
| *(helpers)* | `models/net_utils.py` | shared network helpers |

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

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
- [Connecting to a database (importing cards)](#connecting-to-a-database-importing-cards)
- [Publishing cards to a 3rd-party web host](#publishing-cards-to-a-3rd-party-web-host)
- [Security](#security)
- [Developer reference](#developer-reference)
- [FAQ](#faq)

---

## What you get

| Capability | Where |
|---|---|
| A card per person (name, title, company, email, phone, website, bio, photo) | **Business Cards → Cards** |
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

**Requirements:** Odoo 19, depends only on `base` and `web`. QR generation uses
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
  it instead of the built-in layout. It is **sanitized** (scripts removed) — see
  [Security](#security).
- The public page (`/card/<slug>`) is **public** (no login). It reads the card
  with `sudo()`, so record-level access rules don't block anonymous visitors.

### The fixed link vs the QR code

Like LinkStack, each card has **both**:

- a **fixed, permanent link** — `/<your-odoo>/card/<slug>`, and
- a **QR code** that is generated on demand and simply encodes that link.

The link never changes (as long as the slug stays the same); the QR image is
re-rendered each time it's displayed.

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

## Publishing cards to a 3rd-party web host

You can push the generated cards (data + rendered HTML + QR) to an external
host that will serve them.

### 1. Define where to publish — **Business Cards → Publish Targets → New** *(admin)*

| Field | Meaning |
|---|---|
| Endpoint URL | the 3rd-party address that receives the cards |
| Auth Token | optional; sent as `Authorization: Bearer <token>` |
| Method | `POST` (default) or `PUT` |
| Payload | **JSON** (data + rendered HTML + QR) or **Rendered HTML only** |
| Allow internal addresses | off by default (SSRF guard) |

### 2. Select and send

1. Go to **Business Cards → Cards**.
2. **Tick the checkboxes** of the cards you want to publish.
3. **Actions ▾ → Publish to Web.**
4. Choose the **Destination** (a publish target) and click **Send**.

### What gets sent

**JSON payload** (one request per card):

```json
{
  "slug": "jane",
  "name": "Jane Doe",
  "job_title": "CTO",
  "company": "Acme",
  "email": "jane@acme.com",
  "phone": "+1 555 0100",
  "website": "https://acme.com",
  "bio": "Builder of things.",
  "public_url": "https://your-odoo/card/jane",
  "html": "<!DOCTYPE html> ... full rendered card page ...",
  "qr_png_base64": "iVBORw0KGgo..."
}
```

(With **Rendered HTML only**, the card page is posted as `text/html` instead.)

If the host responds with JSON containing a `url` / `public_url` / `link`, that
value is stored on the card as **Hosted URL**, and **Last Published** records
the time.

---

## Security

This module handles credentials and renders externally-sourced HTML on a public
page, so it was hardened deliberately:

- **No stored XSS** — `source_html` is sanitized on every write (`<script>`,
  `on*` handlers and `javascript:` URLs are stripped; inline styles kept). The
  public `website` link is coerced to `http(s)` so it can't carry a
  `javascript:` payload.
- **SSRF protection** — both the HTTP importer and the publisher refuse
  private/loopback/link-local/reserved IPs unless **Allow internal addresses**
  is explicitly ticked; redirects are disabled so they can't bypass the check.
  (Shared code in `models/net_utils.py`.)
- **Read-only imports** — the PostgreSQL connection runs in a read-only session.
- **Least privilege** — Data Sources and Publish Targets are **admin-only**
  (`base.group_system`). Regular users can only see and edit **their own** cards
  (record rules); admins see all. Secrets use `copy=False`.
- **Size cap** — fetched/sent HTTP bodies are capped at 5 MB.

> **Deployment notes for multi-company / hosted setups:** isolation is currently
> per-*user*. If several companies share one Odoo instance and you need per-
> *company* walls, add a `company_id` + a multi-company record rule. Credentials
> are stored in the DB (same as Odoo's own mail-server passwords) and readable
> only by system admins; if you need encryption-at-rest, that's a separate
> key-management task.

---

## Developer reference

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

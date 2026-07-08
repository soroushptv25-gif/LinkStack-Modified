# Digital Business Card (Odoo 17 module)

A native **Odoo 17** module for shareable **digital business cards** — the
"link in bio" / digital card idea popularised by
[LinkStack](https://github.com/LinkStackOrg/LinkStack).

LinkStack itself is a PHP/Laravel app and **cannot** be dropped into Odoo (Odoo
is Python). This module re-implements the concept natively in Python + XML +
QWeb, and wires it into the **Employees** app so a card can show an employee's
details. It also adds two integrations LinkStack doesn't have:

1. **Import** people (stored as HTML) from an external **PostgreSQL** database.
2. **Publish** selected cards to a **3rd-party web host**.

Each card follows a simple workflow — **Draft → Published → Deactivated**. Once
**published**, it gets a **permanent public link** (`/card/<slug>`), an
**auto-generated QR code**, and an **"Import to contact"** vCard download.
Deactivating switches the link and QR back off.

---

## Table of contents

- [What you get](#what-you-get)
- [Installation](#installation)
- [Quick start](#quick-start)
- [How the module works](#how-the-module-works)
- [Employees & generating cards](#employees--generating-cards)
- [Importing from a database](#importing-from-a-database)
- [Publishing to a 3rd-party host](#publishing-to-a-3rd-party-host)
- [Reference](#reference)
- [FAQ](#faq)

---

## What you get

| Capability | Where |
|---|---|
| Every employee shows in the Cards list **by name** (Draft); **Publish** to create the link + QR | **Business Cards → Cards** |
| Card **workflow**: Draft → Published → Deactivated (deactivate switches the link/QR off) | card form buttons |
| **Kanban & list** views, plus **search / filters** (by status, name, company, position) and group-by | **Business Cards → Cards** |
| A card **linked to an HR employee** — details pulled live, editable per card | the card's **Employee** field |
| Permanent public card page + QR + vCard | `http://<your-odoo>/card/<slug>` |
| Manual **or** automatic card generation | **Business Cards → Card Generation** *(admin)* |
| Import people from an external **PostgreSQL** database | **Business Cards → Data Sources** *(admin)* |
| Publish selected cards to a 3rd-party host | **Cards → Actions ▾ → Publish to Web** |
| Define where to publish | **Business Cards → Publish Targets** *(admin)* |

---

## Installation

The module lives in `addons/`, mounted into the Odoo container at
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

**Requirements:** Odoo 17, depends on `base`, `web` and `hr` (the Employees app
— installed automatically). Everything else ships with Odoo: QR codes use the
built-in barcode engine, the PostgreSQL import uses `psycopg2`, and publishing
uses `requests`. Nothing extra to install.

---

## Quick start

1. Open **Business Cards → Cards**. You'll see **one row per employee** — a
   **Draft** card showing the **name only** (greyed out, no link, no QR).
2. Open a card and click **Publish** (top-left). It gets a **link + QR** and its
   details appear. Open `http://<your-odoo>/card/<slug>` or **Download QR**.
3. To switch a card off, click **Deactivate** — the link/QR stop working (the
   page 404s). **Publish** again to bring it back (same link).
4. Fast path from the Employees app: tick people → **Actions (gear) → Create
   Business Card** (creates + publishes in one step).

---

## How the module works

```
   Employees ──▶ every employee gets a name-only Draft card
                         │
                     Publish  (Draft ▸ Published — link + QR live)
                     Deactivate  (Published ▸ Deactivated — link + QR off)
                         ▼
              ┌───────────────────────────────┐
              │  digital.business.card         │
              │  name, slug, employee_id,      │
              │  contact_* (shown values),     │
              │  source_html                   │
              │  → public_url, qr_code         │
              └───────────────────────────────┘
        external PostgreSQL ─▶ Data Source (import) ─▶ (creates/updates cards)
                         │
   /card/<slug>  ◀───────┤ public QWeb page (auth: public) + /card/<slug>/vcard
                         │
   3rd-party host ◀──────┘ Publish Target (Actions ▸ Publish to Web)
```

- **`digital.business.card`** — one record per person. It starts as a **name-only
  placeholder**; the `slug` (and therefore the link/QR) is empty until you
  **generate** it.
- **`generated`** is `True` once a slug exists.
- **`public_url`** = `web.base.url` + `/card/<slug>` (empty until generated).
- **`qr_code`** is computed from `public_url`, so it always matches the link. It
  is shown on the **card record in Odoo** (the public page itself is kept clean —
  scanning a QR just reopens the same page).
- **`source_html`** — an optional HTML body; when set, the public page renders it
  instead of the built-in layout (it is sanitized on save).
- The public page (`/card/<slug>`) is **public** (no login) and standalone —
  visitors never reach the Odoo backend from it. It is read with `sudo()`.

### Link, QR & vCard
- **Fixed link:** `/card/<slug>` — permanent once generated. Ready to share,
  print, or **write to an NFC tag**.
- **QR code:** auto-generated, encodes that link, shown on the card form.
- **Import to contact:** the public page has a button that downloads the person
  as a **vCard (.vcf)** (`/card/<slug>/vcard`) to save into phone contacts.

---

## Employees & generating cards

Most companies already keep people in Odoo's **Employees** app, so every employee
automatically appears in the Cards list. A card can be linked to an
`hr.employee` and **display its details live** — while outsiders only ever see
the public card page, never the Employees app.

**The card workflow** (buttons at the top of the card form):
- **Publish** — Draft → Published: assigns the slug and turns the **link + QR**
  on. The card's details appear.
- **Deactivate** — Published → Deactivated: turns the link + QR **off** (the
  public page 404s). The slug is kept, so **Publish** again reuses the same link.
- **Reset to Draft** — back to name-only.
- **Download QR** — save the QR PNG (published cards).
- **Update from Employee** — re-sync the shown details from the employee (they
  are live anyway, this is a manual refresh).

From the **Employees** app: tick people → **Actions (gear) → Create Business
Card** creates + publishes in one step.

**Manual vs automatic** — **Business Cards → Card Generation** *(admin)*:
- **Manual (default):** employees appear as Draft (name-only); you publish on demand.
- **Automatic:** turn on *Automatically generate employee cards* and pick the
  scope (future employees only, or all existing now) so new employees are
  **published** immediately.

When a card is linked to an employee, the shown values come from the employee:

| Card shows | Pulled from `hr.employee` |
|---|---|
| Name | `name` |
| Position / Title | `job_title` (falls back to `job_id`) |
| Company | `company_id` |
| Email | `work_email` by default — **configurable** (see below) |
| Phone | `work_phone` (falls back to `mobile_phone`) |
| Photo | `image_1920` |
| Website | the employee's company website |

**Editable per card:** position, email, phone, company, website and photo can be
edited on the card. A value entered there **overrides** the employee's; leave it
blank to use the employee's live value. With no employee linked, the card just
uses its own fields.

### Choosing which employee email the card shows

Odoo's `hr.employee` has two built-in email fields — **`work_email`** and
**`private_email`** (there is no separate "business/second" email field). Which
one feeds the card is controlled by a system parameter, so you can switch it
without changing code:

- **Parameter:** `digital_business_card.employee_email_field`
- **Default:** `work_email` (the original behaviour)
- Set it to **`private_email`** to show the private email instead — or to any
  other `Char` email field on `hr.employee`.
- If the chosen field is empty for an employee, the card falls back to
  `work_email`. A per-card **Email** override always wins.

Set it in **Settings → Technical → System Parameters** (or, if that menu is
hidden, enable Developer Mode). To **revert to the original**, set the value
back to `work_email` (or delete the parameter).

> This instance is configured to use **`private_email`**.

---

## Importing from a database

Import people from an external **PostgreSQL** database whose rows contain an
HTML body. Go to **Business Cards → Data Sources → New** *(admin)* and fill in:

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

Then click **Test Connection**, and **Import Cards** — it reads the rows and
**creates or updates** a card per row (matched by slug, so re-importing
refreshes existing cards). The import only ever reads from the source database.

---

## Publishing to a 3rd-party host

Your cards live inside Odoo at `/card/<slug>`. Publishing lets you *also* push
selected cards to an **external website/API** that stores and serves them.

1. **Business Cards → Publish Targets → New** *(admin)* — define a destination:

   | Field | Meaning |
   |---|---|
   | Endpoint URL | the external address that receives the cards |
   | Auth Token | optional; sent as `Authorization: Bearer <token>` |
   | Method | `POST` (default) or `PUT` |
   | Payload | **JSON** (data + rendered HTML + QR) or **Rendered HTML only** |

2. **Cards → tick cards → Actions ▾ → Publish to Web** → pick the target → **Send**.

Each card is sent to the endpoint. If the host replies with a URL, it is stored
on the card as **Hosted URL** (with a **Last Published** timestamp). The JSON
payload per card looks like:

```json
{ "slug": "jane", "name": "Jane Doe", "job_title": "CTO", "company": "Acme",
  "email": "jane@acme.com", "phone": "+1 555 0100",
  "public_url": "https://your-odoo/card/jane",
  "html": "<full rendered card page>", "qr_png_base64": "iVBORw0KGgo..." }
```

This is optional — if people just open/scan the Odoo `/card/<slug>` link, you
don't need it.

---

## Reference

### Models

| Model | File | Purpose |
|---|---|---|
| `digital.business.card` | `models/business_card.py` | the card; link, QR, vCard |
| `digital.business.card.source` | `models/business_card_source.py` | PostgreSQL import config |
| `digital.business.card.target` | `models/business_card_target.py` | publish destination |
| `digital.business.card.publish.wizard` | `models/business_card_target.py` | "Publish to Web" dialog |
| `digital.business.card.config.wizard` | `models/dbc_config_wizard.py` | manual/automatic generation setting |
| `hr.employee` (extended) | `models/hr_employee.py` | placeholder card per employee |
| *(helpers)* | `models/net_utils.py` | shared URL/size helpers |

### Key methods

| Method | Model | What it does |
|---|---|---|
| `action_publish` / `action_deactivate` / `action_set_draft` | card | workflow transitions (Publish assigns the slug → link + QR) |
| `action_download_qr` / `action_update_from_employee` | card | download the QR PNG / re-sync details from the employee |
| `create_for_employees(employees)` | card | make a name-only Draft card per employee (no duplicates) |
| `_compute_contact` | card | the shown `contact_*` values (employee, overridden by card) |
| `_compute_public_url` / `_compute_qr_code` | card | derive the link and QR from the slug |
| `_build_vcard` | card | render the contact as a vCard 3.0 string |
| `create_card_from_html_file(path, vals)` | card | **dormant** — build a card from a local HTML file (not wired up) |
| `action_test_connection` / `action_import_cards` | source | test / import from PostgreSQL |
| `_publish_cards(cards)` | target | POST/PUT each card to the host |

### Public routes

| Route | Auth | Serves |
|---|---|---|
| `GET /card/<slug>` | public | the public card page |
| `GET /card/<slug>/vcard` | public | the `.vcf` download ("Import to contact") |

---

## FAQ

**Why do employees show with just a name and no link?** A card starts in
**Draft** (name only). **Publish** it (or use automatic mode) to create its link
and QR. **Deactivate** turns them back off.

**Can it generate a QR code, or is the link fixed?** Both — once generated the
link is fixed (`/card/<slug>`) and the QR encodes that link.

**Where is the QR shown?** On the card record inside Odoo. It's deliberately not
on the public page (scanning it would just reopen the same page).

**Can normal users configure imports or publishing?** No — Data Sources, Publish
Targets and Card Generation are admin-only. Regular users manage their own cards.

**What about `create_card_from_html_file`?** It exists but is intentionally
dormant (not called anywhere) — a starting point if you later want to build
cards from local HTML files.

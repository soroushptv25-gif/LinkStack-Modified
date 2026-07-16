# Digital Business Card (Odoo 17 module)

A native **Odoo 17** module for shareable **digital business cards** — the
"link in bio" / digital card idea popularised by
[LinkStack](https://github.com/LinkStackOrg/LinkStack).

LinkStack itself is a PHP/Laravel app and **cannot** be dropped into Odoo (Odoo
is Python). This module re-implements the concept natively in Python + XML +
QWeb, and wires it into the **Employees** app — which is the single source the
cards read their data from. It also adds something LinkStack doesn't have:
**publishing** selected cards to a **3rd-party web host**.

Each card follows a simple workflow — **Draft → Published → Deactivated**. Once
**published**, it gets a **permanent public link** (`/card/<token>`), an
**auto-generated QR code** at an **unguessable hash URL** (`/card/<token>`), and
an **"Import to contact"** vCard download. Deactivating switches the link and QR
back off (the page 404s). Cards can use different **public-page designs**.

---

## Table of contents

- [What you get](#what-you-get)
- [Installation](#installation)
- [Quick start](#quick-start)
- [How the module works](#how-the-module-works)
- [Employees & generating cards](#employees--generating-cards)
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
| Permanent public card page + QR + vCard at an **unguessable hash URL** | `http://<your-odoo>/card/<token>` |
| **Public-page designs** (Classic / Dark / Minimal), per card or a default | card **Public Page Design** / **Settings** |
| **Settings** (email source, default design) | **Business Cards → Configuration → Settings** *(admin)* |
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
built-in barcode engine and publishing uses `requests`. Nothing extra to
install.

---

## Quick start

1. Open **Business Cards → Cards**. You'll see **one row per employee** — a
   **Draft** card showing the **name only** (greyed out, no link, no QR).
2. Open a card and click **Publish** (top-left). It gets a **link + QR** and its
   details appear. Open `http://<your-odoo>/card/<token>` or **Download QR**.
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
                         │
   /card/<token>  ◀───────┤ public QWeb page (auth: public) + /card/<token>/vcard
                         │
   3rd-party host ◀──────┘ Publish Target (Actions ▸ Publish to Web)
```

- **`digital.business.card`** — one record per person. It starts as a **name-only
  placeholder**; the `slug` (and therefore the link/QR) is empty until you
  **generate** it.
- **`generated`** is `True` once a slug exists.
- **`public_url`** = `web.base.url` + `/card/<token>` (empty until published).
- **`qr_code`** is computed from `public_url`, so it always matches the link. It
  is shown on the **card record in Odoo** (the public page itself is kept clean —
  scanning a QR just reopens the same page).
- **`source_html`** — an optional HTML body; when set, the public page renders it
  instead of the built-in layout (it is sanitized on save).
- The public page (`/card/<token>`) is **public** (no login) and standalone —
  visitors never reach the Odoo backend from it. It is read with `sudo()`.

### Link, QR & vCard
- **Fixed link:** `/card/<token>` — a random, **unguessable** hash (so cards
  can't be found by guessing names). Permanent once published; ready to share,
  print, or **write to an NFC tag**. The readable `slug` is a backend-only key.
- **QR code:** auto-generated, encodes that link, shown on the card form.
- **Import to contact:** the public page has a button that downloads the person
  as a **vCard (.vcf)** (`/card/<token>/vcard`) to save into phone contacts.

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

Every new employee automatically gets a **Draft** (name-only) card, so nobody is
missed. Publishing is always a deliberate step — there is no auto-publish.

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

**Main vs Mask (per-field override):** the card form's **Profile** tab has two
sections, side by side, for position, company, email, phone, website and photo:

- **Main — from Employee:** read-only, pulled **live** from the linked employee.
  It updates automatically whenever the employee record changes.
- **Mask — Custom:** editable and **empty by default** (never auto-filled).

The card shows the **Mask** value when it is filled; when a mask is empty it
shows the **Main** (employee) value. So the mask always has priority — and even
if the employee's data changes, a card with a mask set keeps showing the mask
(clear the mask to follow the employee again). The **Shown on the card** tab
previews the resulting values. (Name uses the card's own **Full Name** as its
mask, falling back to the employee's name.)

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

## Publishing to a 3rd-party host

Your cards live inside Odoo at `/card/<token>`. Publishing lets you *also* push
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

This is optional — if people just open/scan the Odoo `/card/<token>` link, you
don't need it.

---

## Reference

### Models

| Model | File | Purpose |
|---|---|---|
| `digital.business.card` | `models/business_card.py` | the card; link, QR, vCard |
| `digital.business.card.target` | `models/business_card_target.py` | publish destination |
| `digital.business.card.publish.wizard` | `models/business_card_target.py` | "Publish to Web" dialog |
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
| `_publish_cards(cards)` | target | POST/PUT each card to the host |

### Public routes

| Route | Auth | Serves |
|---|---|---|
| `GET /card/<token>` | public | the public card page |
| `GET /card/<token>/vcard` | public | the `.vcf` download ("Import to contact") |

---

## FAQ

**Why do employees show with just a name and no link?** A card starts in
**Draft** (name only). **Publish** it (or use automatic mode) to create its link
and QR. **Deactivate** turns them back off.

**Can it generate a QR code, or is the link fixed?** Both — once generated the
link is fixed (`/card/<token>`) and the QR encodes that link.

**If I deactivate a card, does its QR still work?** No — a deactivated (or draft)
card returns **404** at its URL, so a printed/scanned QR stops working. Publish
it again (the same token is reused) to bring it back.

**Can I change the public page design?** Yes — pick **Public Page Design**
(Classic / Dark / Minimal) on the card, or set the default in
**Configuration → Settings**.

**Where is the QR shown?** On the card record inside Odoo. It's deliberately not
on the public page (scanning it would just reopen the same page).

**Can normal users configure publishing?** No — Publish Targets are admin-only.
Regular users manage their own cards.

**What about `create_card_from_html_file`?** It exists but is intentionally
dormant (not called anywhere) — a starting point if you later want to build
cards from local HTML files.

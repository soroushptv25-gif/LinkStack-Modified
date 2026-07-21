# Part of the Digital Business Card module.
import base64
import logging
import os
import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DigitalBusinessCard(models.Model):
    _name = 'digital.business.card'
    _description = 'Digital Business Card'
    _order = 'name asc'

    name = fields.Char(string='Full Name', required=True)
    # The slug is the permanent, shareable handle: the public card lives at
    # /card/<slug>. It is EMPTY until the card is generated — an employee shows
    # in the list by name only until then. Unique + copy=False.
    slug = fields.Char(
        string='Card Link', copy=False, index=True,
        help="Human-readable internal handle (from the name). The PUBLIC url "
             "uses the unguessable access token, not this.")
    # The public page is served at /card/<access_token> — a random, unguessable
    # hash so cards can't be enumerated by guessing names. Generated on publish.
    access_token = fields.Char(
        string='Access Token', copy=False, index=True, readonly=True)
    # Which design the public page uses.
    card_template = fields.Selection(
        [('classic', 'Classic'), ('dark', 'Dark'), ('minimal', 'Minimal')],
        string='Public Page Design', default=lambda self: self._default_template())
    # True once a link/QR has been generated (i.e. a slug exists). Stored so the
    # list can distinguish name-only rows from generated cards.
    generated = fields.Boolean(
        string='Generated', compute='_compute_generated', store=True)
    # Workflow: Draft (name only) -> Published (link + QR live) -> Deactivated
    # (link + QR disabled; the public page 404s).
    state = fields.Selection(
        [('draft', 'Draft'), ('published', 'Published'), ('deactivated', 'Deactivated')],
        string='Status', default='draft', copy=False, index=True,
        help="Draft: name only. Published: the link and QR are live. "
             "Deactivated: the link and QR are switched off.")
    user_id = fields.Many2one(
        'res.users', string='Owner', ondelete='cascade',
        default=lambda self: self.env.user)
    active = fields.Boolean(default=True)

    # Link to an HR employee. When set, the card SHOWS the employee's details
    # (pulled live), so outsiders see the contact via the public card page
    # without ever needing access to the Employees app.
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', ondelete='set null',
        help="When set, the card displays this employee's details (live).")

    bio = fields.Text(string='Bio')

    # --- MAIN fields: read LIVE from the linked employee (read-only). They
    # auto-update whenever the employee record changes. Not stored. ---
    main_name = fields.Char(string='Name (employee)', compute='_compute_main')
    main_job_title = fields.Char(string='Position (employee)', compute='_compute_main')
    main_company = fields.Char(string='Company (employee)', compute='_compute_main')
    main_email = fields.Char(string='Email (employee)', compute='_compute_main')
    main_phone = fields.Char(string='Phone (employee)', compute='_compute_main')
    main_website = fields.Char(string='Website (employee)', compute='_compute_main')
    main_photo = fields.Binary(string='Photo (employee)', compute='_compute_main')

    # --- MASK fields: the user's own values. Editable, empty by default, never
    # auto-filled. When a mask is set it OVERRIDES the employee value on the
    # card; when empty the employee (main) value is shown instead. ---
    mask_job_title = fields.Char(string='Position (mask)')
    mask_company = fields.Char(string='Company (mask)')
    mask_email = fields.Char(string='Email (mask)')
    mask_phone = fields.Char(string='Phone (mask)')
    mask_website = fields.Char(string='Website (mask)')
    mask_photo = fields.Binary(string='Photo (mask)', attachment=True)

    # What actually gets shown on the card = mask if set, else the employee
    # (main) value. Computed (not stored). For name, the record's own `name`
    # acts as the mask, falling back to the employee name.
    contact_name = fields.Char(string='Shown Name', compute='_compute_contact',
                               search='_search_contact_name')
    contact_job_title = fields.Char(string='Shown Title', compute='_compute_contact',
                                    search='_search_contact_job_title')
    contact_company = fields.Char(string='Shown Company', compute='_compute_contact',
                                  search='_search_contact_company')
    contact_email = fields.Char(string='Shown Email', compute='_compute_contact')
    contact_phone = fields.Char(string='Shown Phone', compute='_compute_contact')
    contact_website = fields.Char(string='Shown Website', compute='_compute_contact')
    contact_image = fields.Binary(string='Shown Photo', compute='_compute_contact')

    # Optional HTML body. When present, the public page renders this instead
    # of the built-in layout. It can come from UNTRUSTED external sources, so
    # it is sanitized on write (scripts, on* handlers and javascript: URLs are
    # stripped) while inline styles/classes are kept for layout. Never set
    # sanitize=False here — this field is shown on a public, unauthenticated
    # page and raw HTML would be a stored-XSS hole.
    source_html = fields.Html(
        string='Custom HTML', sanitize=True, sanitize_attributes=True,
        strip_style=False, strip_classes=False)
    # Upload an .html file and load it into the design above.
    html_file = fields.Binary(string='HTML File', attachment=True)
    html_filename = fields.Char(string='HTML File Name')

    # Guided design controls: which preset the design came from, plus the accent
    # colour and width applied to it. Changing accent/width regenerates the
    # preset design live (only for preset-based designs, not custom/uploaded).
    design_preset = fields.Selection(
        [('card', 'Card'), ('banner', 'Banner'), ('split', 'Split'), ('modern', 'Modern')],
        string='Design Preset', copy=False)
    design_accent = fields.Selection(
        [('indigo', 'Indigo'), ('purple', 'Purple'), ('teal', 'Teal'),
         ('rose', 'Rose'), ('slate', 'Slate'), ('amber', 'Amber')],
        string='Accent Color', default='indigo')
    design_width = fields.Selection(
        [('narrow', 'Narrow'), ('normal', 'Normal'), ('wide', 'Wide')],
        string='Card Width', default='normal')
    design_bg = fields.Selection(
        [('white', 'White'), ('light', 'Light Gray'), ('cream', 'Cream'),
         ('slate', 'Slate'), ('ink', 'Ink (dark)')],
        string='Background Color', default='white')

    # Permanent public link + the QR code that points at it. Each card has its
    # own unique link/QR — share it, print the QR, or write the URL to an NFC
    # tag. It opens the standalone public card page; visitors never reach the
    # Odoo backend from it.
    public_url = fields.Char(
        string='Public URL', compute='_compute_public_url',
        help="Per-card public link. Share it, print its QR, or write it to an NFC tag.")
    qr_code = fields.Binary(string='QR Code', compute='_compute_qr_code')
    # Scheme-safe version of `website` for use in a public <a href>: anything
    # that is not plainly http(s) is coerced to https:// so a "javascript:"
    # value can never become a clickable XSS payload.
    website_url = fields.Char(string='Website URL', compute='_compute_website_url')

    # Set when the card is pushed to a 3rd-party host (see publish target).
    last_published = fields.Datetime(string='Last Published', readonly=True, copy=False)
    published_url = fields.Char(string='Hosted URL', readonly=True, copy=False,
                                help="Where the 3rd-party host published this card, if it returned one.")

    _sql_constraints = [
        ('unique_slug', 'unique(slug)',
         "That card link is already taken — please choose another one."),
    ]

    @api.depends('slug')
    def _compute_generated(self):
        for card in self:
            card.generated = bool(card.slug)

    @api.model
    def _default_template(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'digital_business_card.default_template') or 'classic'

    @api.depends('access_token', 'state')
    def _compute_public_url(self):
        # The link only exists while the card is PUBLISHED, and it uses the
        # unguessable access token (a hash), never the readable slug.
        # Deactivating (or reverting to draft) blanks the link and QR — 404.
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for card in self:
            live = card.access_token and card.state == 'published'
            card.public_url = '%s/card/%s' % (base, card.access_token) if live else False

    @api.depends('employee_id',
                 'employee_id.name', 'employee_id.job_title', 'employee_id.job_id',
                 'employee_id.company_id', 'employee_id.work_email',
                 'employee_id.private_email',
                 'employee_id.work_phone', 'employee_id.mobile_phone',
                 'employee_id.image_1920')
    def _compute_main(self):
        # MAIN = the linked employee's live values (read-only). These update
        # automatically whenever the employee record changes.
        #
        # Which employee email feeds the card is configurable via the system
        # parameter 'digital_business_card.employee_email_field' (default
        # 'work_email'; set to 'private_email' to use the private email). Falls
        # back to work_email if the chosen field is empty/invalid.
        email_field = self.env['ir.config_parameter'].sudo().get_param(
            'digital_business_card.employee_email_field') or 'work_email'
        for card in self:
            emp = card.employee_id.sudo() if card.employee_id else False
            if not emp:
                card.main_name = card.main_job_title = card.main_company = False
                card.main_email = card.main_phone = card.main_website = False
                card.main_photo = False
                continue
            chosen = emp[email_field] if email_field in emp._fields else False
            card.main_name = emp.name or False
            card.main_job_title = emp.job_title or (emp.job_id.name or False)
            card.main_company = emp.company_id.name or False
            card.main_email = chosen or emp.work_email or False
            card.main_phone = emp.work_phone or emp.mobile_phone or False
            card.main_website = emp.company_id.website or False
            card.main_photo = emp.image_1920 or False

    @api.depends('slug', 'name',
                 'main_name', 'main_job_title', 'main_company', 'main_email',
                 'main_phone', 'main_website', 'main_photo',
                 'mask_job_title', 'mask_company', 'mask_email', 'mask_phone',
                 'mask_website', 'mask_photo')
    def _compute_contact(self):
        # Shown value = MASK if set, otherwise MAIN (employee). The mask always
        # wins; only when it is empty do we fall back to the employee value.
        # Name is special: the record's own `name` is its mask.
        # Details other than the name only appear once the card is generated
        # (has a slug) — a draft shows the name only.
        for card in self:
            card.contact_name = card.name or card.main_name
            if not card.slug:
                card.contact_job_title = card.contact_company = False
                card.contact_email = card.contact_phone = False
                card.contact_website = card.contact_image = False
                continue
            card.contact_job_title = card.mask_job_title or card.main_job_title
            card.contact_company = card.mask_company or card.main_company
            card.contact_email = card.mask_email or card.main_email
            card.contact_phone = card.mask_phone or card.main_phone
            card.contact_website = card.mask_website or card.main_website
            card.contact_image = card.mask_photo or card.main_photo

    # Make the shown values searchable: match the mask value OR the employee's.
    def _search_contact_name(self, operator, value):
        return ['|', ('name', operator, value), ('employee_id.name', operator, value)]

    def _search_contact_company(self, operator, value):
        return ['|', ('mask_company', operator, value),
                ('employee_id.company_id.name', operator, value)]

    def _search_contact_job_title(self, operator, value):
        return ['|', '|', ('mask_job_title', operator, value),
                ('employee_id.job_title', operator, value),
                ('employee_id.job_id.name', operator, value)]

    @api.depends('contact_website')
    def _compute_website_url(self):
        for card in self:
            raw = (card.contact_website or '').strip()
            if not raw:
                card.website_url = False
            elif raw.lower().startswith(('http://', 'https://')):
                card.website_url = raw
            else:
                # Drops dangerous schemes (javascript:, data:, ...) by forcing
                # the value to look like an external https link.
                card.website_url = 'https://' + raw.split('://', 1)[-1]

    @api.depends('public_url')
    def _compute_qr_code(self):
        # Odoo bundles a barcode engine; 'QR' encodes the permanent link as a
        # PNG. The QR is computed (not stored), so it always tracks the link.
        report = self.env['ir.actions.report']
        for card in self:
            if not card.public_url:
                card.qr_code = False
                continue
            try:
                png = report.barcode('QR', card.public_url, width=400, height=400)
                card.qr_code = base64.b64encode(png)
            except Exception:
                _logger.warning("Could not generate QR code for card %s", card.id)
                card.qr_code = False

    # ------------------------------------------------------------------
    # Creation helpers — make "a card per employee" effortless.
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            emp = (self.env['hr.employee'].browse(vals['employee_id'])
                   if vals.get('employee_id') else False)
            if emp:
                # Default the record label and owner from the employee. The slug
                # is left empty on purpose — the card is a name-only placeholder
                # until it is generated.
                vals.setdefault('name', emp.name)
                if not vals.get('user_id') and emp.user_id:
                    vals['user_id'] = emp.user_id.id
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow: draft -> published -> deactivated
    # ------------------------------------------------------------------
    def action_publish(self):
        """Draft/Deactivated -> Published: assign a readable slug + an
        unguessable access token (the public hash URL) if missing, then go live.
        The token is reused across re-publish so a printed QR keeps working."""
        for card in self:
            if not card.slug:
                base = card.name or (card.employee_id.name if card.employee_id else 'card')
                card.slug = self._unique_slug(base)
            if not card.access_token:
                card.access_token = uuid.uuid4().hex
        self.write({'state': 'published'})
        return True

    def action_deactivate(self):
        """Published -> Deactivated: switch the link + QR off (page 404s). The
        slug is kept so re-publishing reuses the same link."""
        self.write({'state': 'deactivated'})
        return True

    def action_set_draft(self):
        """Back to Draft (name only)."""
        self.write({'state': 'draft'})
        return True

    def action_update_from_employee(self):
        """Refresh the shown details from the linked employee's current data.
        (The details are live-computed, so this is a manual re-sync.)"""
        self.invalidate_recordset([
            'contact_name', 'contact_job_title', 'contact_company', 'contact_email',
            'contact_phone', 'contact_website', 'contact_image'])
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': 'Updated',
                       'message': 'Card details refreshed from the employee.',
                       'type': 'success', 'sticky': False},
        }

    def action_download_qr(self):
        """Download the QR code PNG for this card."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/image/digital.business.card/%s/qr_code?download=true'
                   '&filename=%s-qr.png' % (self.id, self.slug or 'card'),
            'target': 'new',
        }

    def action_open_public(self):
        """Open the public card page in a new tab."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.public_url or '/',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Public-page design presets. Each loads a ready-made, personalised HTML
    # layout into the Design tab (source_html); the user then edits it live.
    # ------------------------------------------------------------------
    # Accent colours -> (solid, gradient-end) hex. Card width -> px.
    _ACCENT_HEX = {
        'indigo': ('#4f46e5', '#7c3aed'),
        'purple': ('#7c3aed', '#a855f7'),
        'teal': ('#0d9488', '#14b8a6'),
        'rose': ('#e11d48', '#f43f5e'),
        'slate': ('#0f172a', '#334155'),
        'amber': ('#d97706', '#f59e0b'),
    }
    _WIDTH_PX = {'narrow': 380, 'normal': 440, 'wide': 560}
    # Body ("white part") background -> (bg, text, contact-pill bg, link colour).
    # link=None means "use the accent colour"; a value overrides it for contrast
    # on dark backgrounds.
    _BG = {
        'white': ('#ffffff', '#374151', '#f5f5ff', None),
        'light': ('#f3f4f6', '#374151', '#ffffff', None),
        'cream': ('#fdf6ec', '#4b3f2f', '#fff8ee', None),
        'slate': ('#1e293b', '#e5e7eb', '#334155', '#ffffff'),
        'ink': ('#0f172a', '#cbd5e1', '#1e293b', '#ffffff'),
    }

    def _apply_preset(self, kind):
        for card in self:
            card.design_preset = kind
            card.source_html = card._preset_html(kind)
        return True

    def action_preset_card(self):
        return self._apply_preset('card')

    def action_preset_banner(self):
        return self._apply_preset('banner')

    def action_preset_split(self):
        return self._apply_preset('split')

    def action_preset_modern(self):
        return self._apply_preset('modern')

    def action_preset_clear(self):
        for card in self:
            card.design_preset = False
            card.source_html = False
        return True

    @api.onchange('design_accent', 'design_width', 'design_bg')
    def _onchange_design_style(self):
        # Live recolour/resize: regenerate the preset design when the accent or
        # width changes — but only for preset-based designs, so a custom or
        # uploaded HTML design is never overwritten.
        for card in self:
            if card.design_preset:
                card.source_html = card._preset_html(card.design_preset)

    def action_load_html_file(self):
        """Load an uploaded .html file into the public-page design. The content
        goes through source_html, which is sanitized on write (scripts stripped,
        layout kept), so it's safe to show on the public page."""
        self.ensure_one()
        if not self.html_file:
            raise UserError("Upload an HTML file first.")
        try:
            content = base64.b64decode(self.html_file).decode('utf-8', 'replace')
        except Exception as e:
            raise UserError("Could not read the HTML file: %s" % e)
        self.design_preset = False   # custom design — don't auto-regenerate it
        self.source_html = content
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': 'Loaded',
                       'message': 'The HTML file is now the public-page design.',
                       'type': 'success', 'sticky': False},
        }

    def _preset_values(self):
        """Data for the presets — masks override the employee, ungated by state
        so presets work in Draft too. Includes the chosen accent + width."""
        from markupsafe import escape
        website = self.mask_website or self.main_website or ''
        if website and not website.lower().startswith(('http://', 'https://')):
            website = 'https://' + website
        solid, grad = self._ACCENT_HEX.get(self.design_accent or 'indigo',
                                           self._ACCENT_HEX['indigo'])
        bg, text, pill, link = self._BG.get(self.design_bg or 'white',
                                            self._BG['white'])
        return {
            'img': '/web/image/digital.business.card/%s/contact_image' % (self.id or 0),
            'name': escape(self.name or self.main_name or 'Your Name'),
            'title': escape(self.mask_job_title or self.main_job_title or 'Job Title'),
            'company': escape(self.mask_company or self.main_company or 'Company'),
            'email': escape(self.mask_email or self.main_email or 'name@company.com'),
            'phone': escape(self.mask_phone or self.main_phone or '+1 000 000 0000'),
            'website': escape(website),
            'solid': solid, 'grad': grad,
            'w': self._WIDTH_PX.get(self.design_width or 'normal', 440),
            'bg': bg, 'text': text, 'pill': pill, 'link': link or solid,
        }

    def _preset_html(self, kind):
        self.ensure_one()
        v = self._preset_values()
        if kind == 'banner':
            return (
                '<div style="max-width:%(w)spx;margin:0 auto;font-family:sans-serif;'
                'box-shadow:0 10px 30px rgba(0,0,0,.1);border-radius:16px;overflow:hidden;">'
                '<div style="background:linear-gradient(135deg,%(solid)s,%(grad)s);'
                'color:#fff;padding:44px 24px;text-align:center;">'
                '<img src="%(img)s" style="width:110px;height:110px;border-radius:50%%;'
                'object-fit:cover;border:4px solid rgba(255,255,255,.4);"/>'
                '<h1 style="margin:14px 0 4px;">%(name)s</h1>'
                '<p style="margin:0;opacity:.9;">%(title)s</p></div>'
                '<div style="padding:24px;background:%(bg)s;text-align:center;color:%(text)s;">'
                '<p style="font-weight:600;margin:0 0 12px;">%(company)s</p>'
                '<p style="margin:6px 0;">✉ <a href="mailto:%(email)s" style="color:%(link)s;">%(email)s</a></p>'
                '<p style="margin:6px 0;">☎ <a href="tel:%(phone)s" style="color:%(link)s;">%(phone)s</a></p>'
                '<p style="margin:6px 0;">🌐 <a href="%(website)s" style="color:%(link)s;">%(website)s</a></p>'
                '</div></div>') % v
        if kind == 'split':
            return (
                '<div class="container" style="max-width:%(w)spx;margin:40px auto;font-family:sans-serif;">'
                '<div class="row g-0" style="background:%(bg)s;border-radius:16px;overflow:hidden;'
                'box-shadow:0 10px 30px rgba(0,0,0,.1);">'
                '<div class="col-5" style="background:%(solid)s;color:#fff;padding:32px;text-align:center;">'
                '<img src="%(img)s" style="width:110px;height:110px;border-radius:50%%;object-fit:cover;"/>'
                '<h2 style="margin:16px 0 4px;font-size:1.3rem;">%(name)s</h2>'
                '<p style="margin:0;opacity:.8;">%(title)s</p></div>'
                '<div class="col-7" style="padding:32px;color:%(text)s;">'
                '<h3 style="margin:0 0 16px;">%(company)s</h3>'
                '<p style="margin:8px 0;">✉ <a href="mailto:%(email)s" style="color:%(link)s;">%(email)s</a></p>'
                '<p style="margin:8px 0;">☎ <a href="tel:%(phone)s" style="color:%(link)s;">%(phone)s</a></p>'
                '<p style="margin:8px 0;">🌐 <a href="%(website)s" style="color:%(link)s;">%(website)s</a></p>'
                '</div></div></div>') % v
        if kind == 'modern':
            return (
                '<div style="max-width:%(w)spx;margin:40px auto;font-family:-apple-system,'
                '\'Segoe UI\',Roboto,Arial,sans-serif;border-radius:20px;overflow:hidden;'
                'box-shadow:0 20px 55px rgba(0,0,0,.16);background:%(bg)s;">'
                '<div style="background:linear-gradient(135deg,%(grad)s 0%%,%(solid)s 100%%);'
                'padding:42px 24px 58px;text-align:center;">'
                '<img src="%(img)s" style="width:112px;height:112px;border-radius:50%%;'
                'object-fit:cover;border:4px solid rgba(255,255,255,.85);'
                'box-shadow:0 8px 22px rgba(0,0,0,.22);"/>'
                '<h1 style="color:#fff;margin:16px 0 4px;font-size:1.7rem;">%(name)s</h1>'
                '<p style="color:rgba(255,255,255,.88);margin:0;">%(title)s</p></div>'
                '<div style="padding:26px 24px 12px;margin-top:-22px;background:%(bg)s;'
                'border-radius:22px 22px 0 0;color:%(text)s;">'
                '<a href="mailto:%(email)s" style="display:block;padding:14px 18px;margin:10px 0;'
                'border-radius:12px;background:%(pill)s;color:%(link)s;text-decoration:none;'
                'font-weight:500;">✉ %(email)s</a>'
                '<a href="tel:%(phone)s" style="display:block;padding:14px 18px;margin:10px 0;'
                'border-radius:12px;background:%(pill)s;color:%(link)s;text-decoration:none;'
                'font-weight:500;">☎ %(phone)s</a>'
                '<a href="%(website)s" style="display:block;padding:14px 18px;margin:10px 0;'
                'border-radius:12px;background:%(pill)s;color:%(link)s;text-decoration:none;'
                'font-weight:500;">🌐 %(website)s</a></div>'
                '<div style="background:#0f172a;padding:16px;text-align:center;">'
                '<p style="color:#94a3b8;margin:0;font-size:.85rem;">%(company)s</p></div>'
                '</div>') % v
        # default: 'card'
        return (
            '<div style="max-width:%(w)spx;margin:40px auto;padding:32px;background:%(bg)s;'
            'border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.08);text-align:center;'
            'font-family:sans-serif;color:%(text)s;border-top:5px solid %(solid)s;">'
            '<img src="%(img)s" style="width:120px;height:120px;border-radius:50%%;'
            'object-fit:cover;margin-bottom:16px;border:3px solid %(solid)s;"/>'
            '<h1 style="margin:0;font-size:1.6rem;">%(name)s</h1>'
            '<p style="margin:6px 0 20px;opacity:.75;">%(title)s · %(company)s</p>'
            '<p style="margin:8px 0;">✉ <a href="mailto:%(email)s" style="color:%(link)s;">%(email)s</a></p>'
            '<p style="margin:8px 0;">☎ <a href="tel:%(phone)s" style="color:%(link)s;">%(phone)s</a></p>'
            '<p style="margin:8px 0;">🌐 <a href="%(website)s" style="color:%(link)s;">%(website)s</a></p>'
            '</div>') % v

    def _unique_slug(self, base):
        """Build a URL-safe, unique slug from a name."""
        import re
        root = re.sub(r'[^a-z0-9]+', '-', (base or 'card').lower()).strip('-') or 'card'
        candidate, n = root, 1
        Card = self.with_context(active_test=False)
        while Card.search([('slug', '=', candidate)], limit=1):
            n += 1
            candidate = '%s-%d' % (root, n)
        return candidate

    @api.model
    def create_for_employees(self, employees):
        """Create one card per employee (skipping those that already have one).
        Returns the cards for the given employees (existing + newly created)."""
        cards = self.browse()
        for emp in employees:
            existing = self.search([('employee_id', '=', emp.id)], limit=1)
            cards |= existing or self.create({'employee_id': emp.id})
        return cards

    # ------------------------------------------------------------------
    # vCard (.vcf) — lets a card viewer save the contact to their phone.
    # ------------------------------------------------------------------
    def _build_vcard(self):
        """Return this card as a vCard 3.0 string (with the photo if any)."""
        self.ensure_one()

        def esc(value):
            return (str(value or '')
                    .replace('\\', '\\\\').replace('\n', '\\n')
                    .replace(',', '\\,').replace(';', '\\;'))

        name = self.contact_name or self.name or self.slug or 'Contact'
        lines = ['BEGIN:VCARD', 'VERSION:3.0',
                 'N:%s;;;;' % esc(name), 'FN:%s' % esc(name)]
        if self.contact_company:
            lines.append('ORG:%s' % esc(self.contact_company))
        if self.contact_job_title:
            lines.append('TITLE:%s' % esc(self.contact_job_title))
        if self.contact_email:
            lines.append('EMAIL;TYPE=INTERNET:%s' % esc(self.contact_email))
        if self.contact_phone:
            lines.append('TEL;TYPE=CELL:%s' % esc(self.contact_phone))
        if self.website_url:
            lines.append('URL:%s' % esc(self.website_url))
        if self.public_url:
            lines.append('URL:%s' % esc(self.public_url))
        if self.contact_image:
            try:
                raw = base64.b64decode(self.contact_image)
                ptype = 'PNG' if raw[:4] == b'\x89PNG' else (
                    'JPEG' if raw[:3] == b'\xff\xd8\xff' else None)
                if ptype:
                    b64 = self.contact_image.decode() if isinstance(
                        self.contact_image, bytes) else self.contact_image
                    lines.append('PHOTO;ENCODING=b;TYPE=%s:%s' % (ptype, b64))
            except Exception:
                pass
        lines.append('END:VCARD')

        # Fold lines longer than 75 chars (RFC 6350): continuation starts with
        # a single space. Mainly matters for the base64 photo.
        folded = []
        for line in lines:
            while len(line) > 75:
                folded.append(line[:75])
                line = ' ' + line[75:]
            folded.append(line)
        return '\r\n'.join(folded) + '\r\n'

    # ------------------------------------------------------------------
    # Dormant: HTML -> card importer.
    #
    # Reads an HTML file (e.g. an exported LinkStack/Linktree card or any
    # hand-made template) and creates a card whose public page renders that
    # HTML verbatim. This is intentionally NOT called from any button, route
    # or cron yet — it is parked here for later use, as requested.
    # ------------------------------------------------------------------
    @api.model
    def create_card_from_html_file(self, file_path, vals=None):
        """Create a card from an HTML file on the server filesystem.

        :param str file_path: absolute path to a readable ``.html`` file.
        :param dict vals: extra field values (name, slug, user_id, ...).
        :returns: the created ``digital.business.card`` record.

        Dormant on purpose — not invoked anywhere in the module.
        """
        if not file_path or not os.path.isfile(file_path):
            raise UserError("HTML file not found: %s" % file_path)
        with open(file_path, 'r', encoding='utf-8') as fh:
            html = fh.read()
        return self._create_card_from_html(html, vals=vals)

    @api.model
    def _create_card_from_html(self, html, vals=None):
        """Build a card record from a raw HTML string. Dormant helper."""
        values = dict(vals or {})
        values.setdefault('name', 'Imported Card')
        values.setdefault(
            'slug', 'card-%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S'))
        values['source_html'] = html
        return self.create(values)

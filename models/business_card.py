# Part of the Digital Business Card module.
import base64
import logging
import os

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
        help="URL-safe handle, assigned when the card is generated. "
             "The public card is then served at /card/<slug>.")
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

    # Manual details — used as the card's own data, and as the fallback when no
    # employee is linked.
    job_title = fields.Char(string='Job Title')
    company = fields.Char(string='Company')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    website = fields.Char(string='Website')
    bio = fields.Text(string='Bio')
    photo = fields.Binary(string='Photo', attachment=True)

    # What actually gets shown on the card: the linked employee's data when
    # present, otherwise the manual fields above. Computed (not stored) so they
    # always reflect the current employee record. The employee is read with
    # sudo() so a public visitor — who has no access to hr.employee — still
    # sees the published contact details.
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

    @api.depends('slug', 'state')
    def _compute_public_url(self):
        # The link only exists while the card is PUBLISHED. Deactivating (or
        # reverting to draft) blanks the link and QR — the public page 404s.
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for card in self:
            live = card.slug and card.state == 'published'
            card.public_url = '%s/card/%s' % (base, card.slug) if live else False

    @api.depends('slug', 'employee_id', 'name', 'job_title', 'company', 'email', 'phone',
                 'website', 'photo',
                 'employee_id.name', 'employee_id.job_title', 'employee_id.job_id',
                 'employee_id.company_id', 'employee_id.work_email',
                 'employee_id.work_phone', 'employee_id.mobile_phone',
                 'employee_id.image_1920')
    def _compute_contact(self):
        # The NAME always shows (that's the name-only placeholder row). The rest
        # of the details only appear once the card is generated (has a slug).
        # For a generated card the override model applies: a value entered on the
        # card wins; when blank, the linked employee's live value is used.
        for card in self:
            emp = card.employee_id.sudo() if card.employee_id else False
            card.contact_name = card.name or (emp.name if emp else False)
            if not card.slug:
                card.contact_job_title = card.contact_company = False
                card.contact_email = card.contact_phone = False
                card.contact_website = card.contact_image = False
                continue
            emp_title = (emp.job_title or (emp.job_id.name or False)) if emp else False
            card.contact_job_title = card.job_title or emp_title
            card.contact_company = card.company or (emp.company_id.name if emp else False)
            card.contact_email = card.email or (emp.work_email if emp else False)
            card.contact_phone = card.phone or (
                (emp.work_phone or emp.mobile_phone) if emp else False)
            card.contact_website = card.website or (
                emp.company_id.website if emp else False)
            card.contact_image = card.photo or (emp.image_1920 if emp else False)

    # Make the shown values searchable: match the card's own field OR the
    # linked employee's, so the search box finds either source.
    def _search_contact_name(self, operator, value):
        return ['|', ('name', operator, value), ('employee_id.name', operator, value)]

    def _search_contact_company(self, operator, value):
        return ['|', ('company', operator, value),
                ('employee_id.company_id.name', operator, value)]

    def _search_contact_job_title(self, operator, value):
        return ['|', '|', ('job_title', operator, value),
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
        """Draft/Deactivated -> Published: assign a slug if missing (creating
        the link + QR) and go live."""
        for card in self:
            if not card.slug:
                base = card.name or (card.employee_id.name if card.employee_id else 'card')
                card.slug = self._unique_slug(base)
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

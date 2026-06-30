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
    # /card/<slug>. Kept unique and copy=False so duplicating a card asks for
    # a fresh link instead of clashing.
    slug = fields.Char(
        string='Card Link', required=True, copy=False, index=True,
        help="URL-safe handle. The public card is served at /card/<slug>.")
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
    contact_name = fields.Char(string='Shown Name', compute='_compute_contact')
    contact_job_title = fields.Char(string='Shown Title', compute='_compute_contact')
    contact_company = fields.Char(string='Shown Company', compute='_compute_contact')
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

    _unique_slug = models.Constraint(
        'unique(slug)',
        "That card link is already taken — please choose another one.",
    )

    @api.depends('slug')
    def _compute_public_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for card in self:
            card.public_url = '%s/card/%s' % (base, card.slug) if card.slug else False

    @api.depends('employee_id', 'name', 'job_title', 'company', 'email', 'phone',
                 'website', 'photo',
                 'employee_id.name', 'employee_id.job_title', 'employee_id.job_id',
                 'employee_id.company_id', 'employee_id.work_email',
                 'employee_id.work_phone', 'employee_id.mobile_phone',
                 'employee_id.image_1920')
    def _compute_contact(self):
        for card in self:
            emp = card.employee_id.sudo() if card.employee_id else False
            if emp:
                card.contact_name = emp.name or card.name
                card.contact_job_title = emp.job_title or (emp.job_id.name or False)
                card.contact_company = emp.company_id.name or False
                card.contact_email = emp.work_email or False
                card.contact_phone = emp.work_phone or emp.mobile_phone or False
                card.contact_website = emp.company_id.website or False
                card.contact_image = emp.image_1920 or False
            else:
                card.contact_name = card.name
                card.contact_job_title = card.job_title
                card.contact_company = card.company
                card.contact_email = card.email
                card.contact_phone = card.phone
                card.contact_website = card.website
                card.contact_image = card.photo

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
                # Default the record label and owner from the employee.
                vals.setdefault('name', emp.name)
                if not vals.get('user_id') and emp.user_id:
                    vals['user_id'] = emp.user_id.id
            if not vals.get('slug'):
                base = vals.get('name') or (emp.name if emp else 'card')
                vals['slug'] = self._unique_slug(base)
        return super().create(vals_list)

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

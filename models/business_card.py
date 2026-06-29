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

    # Details rendered on the card.
    job_title = fields.Char(string='Job Title')
    company = fields.Char(string='Company')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    website = fields.Char(string='Website')
    bio = fields.Text(string='Bio')
    photo = fields.Binary(string='Photo', attachment=True)

    # Optional HTML body. When present, the public page renders this instead
    # of the built-in layout. It can come from UNTRUSTED external sources, so
    # it is sanitized on write (scripts, on* handlers and javascript: URLs are
    # stripped) while inline styles/classes are kept for layout. Never set
    # sanitize=False here — this field is shown on a public, unauthenticated
    # page and raw HTML would be a stored-XSS hole.
    source_html = fields.Html(
        string='Custom HTML', sanitize=True, sanitize_attributes=True,
        strip_style=False, strip_classes=False)

    # Permanent public link + the QR code that points at it.
    public_url = fields.Char(string='Public URL', compute='_compute_public_url')
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

    @api.depends('website')
    def _compute_website_url(self):
        for card in self:
            raw = (card.website or '').strip()
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

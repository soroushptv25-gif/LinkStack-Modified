# Part of the Digital Business Card module.
#
# Outbound side: a "publish target" is a 3rd-party web address that hosts the
# generated cards. The user ticks the cards they want in the list view and
# sends them here. Admin-only, because it holds upload credentials.
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from .net_utils import assert_url_allowed

_logger = logging.getLogger(__name__)


class DigitalBusinessCardTarget(models.Model):
    _name = 'digital.business.card.target'
    _description = 'Business Card Publish Target'
    _order = 'name asc'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    url = fields.Char(string='Endpoint URL', required=True,
                      help="3rd-party address that receives the cards.")
    auth_token = fields.Char(string='Auth Token (optional)', copy=False,
                             help="Sent as 'Authorization: Bearer <token>'.")
    http_method = fields.Selection([('post', 'POST'), ('put', 'PUT')],
                                   string='Method', default='post', required=True)
    payload_format = fields.Selection(
        [('json', 'JSON (data + rendered HTML + QR)'),
         ('html', 'Rendered HTML only')],
        string='Payload', default='json', required=True)
    allow_private = fields.Boolean(
        string='Allow internal addresses', default=False,
        help="Permit publishing to private/internal IPs. Leave off unless "
             "you trust the target network.")

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------
    def _publish_cards(self, cards):
        """Send each card to this target. Returns (ok_count, fail_count)."""
        self.ensure_one()
        assert_url_allowed(self.url, self.allow_private)
        headers = {}
        if self.auth_token:
            headers['Authorization'] = 'Bearer %s' % self.auth_token
        ok = fail = 0
        for card in cards:
            try:
                if self.payload_format == 'html':
                    body = self._render_card_html(card).encode('utf-8')
                    resp = self._send(
                        dict(headers, **{'Content-Type': 'text/html; charset=utf-8'}),
                        data=body)
                else:
                    resp = self._send(headers, json=self._card_payload(card))
                resp.raise_for_status()
                card.write({
                    'last_published': fields.Datetime.now(),
                    'published_url': self._extract_url(resp) or self.url,
                })
                ok += 1
            except Exception as e:
                _logger.warning("Publish failed for card %s to %s: %s",
                                card.id, self.name, e)
                fail += 1
        return ok, fail

    def _send(self, headers, json=None, data=None):
        import requests  # ships with Odoo
        method = requests.post if self.http_method == 'post' else requests.put
        # allow_redirects=False so a redirect can't quietly retarget the upload.
        return method(self.url, headers=headers, json=json, data=data,
                      timeout=20, allow_redirects=False)

    def _card_payload(self, card):
        """JSON body for one card: details + permanent link + rendered HTML + QR."""
        return {
            'slug': card.slug,
            'name': card.contact_name or '',
            'job_title': card.contact_job_title or '',
            'company': card.contact_company or '',
            'email': card.contact_email or '',
            'phone': card.contact_phone or '',
            'website': card.website_url or '',
            'bio': card.bio or '',
            'public_url': card.public_url or '',
            'html': self._render_card_html(card),
            'qr_png_base64': card.qr_code.decode() if card.qr_code else '',
        }

    def _render_card_html(self, card):
        """Render the public card page to a standalone HTML string."""
        return self.env['ir.qweb']._render(
            'digital_business_card.card_public_page', {'card': card})

    def _extract_url(self, resp):
        """Best-effort: read a hosted URL the 3rd party may return as JSON."""
        try:
            data = resp.json()
        except Exception:
            return None
        if isinstance(data, dict):
            return data.get('url') or data.get('public_url') or data.get('link')
        return None


class DigitalBusinessCardPublishWizard(models.TransientModel):
    _name = 'digital.business.card.publish.wizard'
    _description = 'Publish Business Cards'

    target_id = fields.Many2one(
        'digital.business.card.target', string='Destination', required=True)
    card_ids = fields.Many2many('digital.business.card', string='Cards')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('active_model') == 'digital.business.card' and ctx.get('active_ids'):
            res['card_ids'] = [(6, 0, ctx['active_ids'])]
        return res

    def action_publish(self):
        self.ensure_one()
        if not self.card_ids:
            raise UserError("Please select at least one card to publish.")
        ok, fail = self.target_id._publish_cards(self.card_ids)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Publish to Web',
                'message': '%s card(s) sent, %s failed.' % (ok, fail),
                'type': 'success' if not fail else 'warning',
                'sticky': False,
            },
        }

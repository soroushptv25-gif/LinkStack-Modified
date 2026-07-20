# Part of the Digital Business Card module.
from markupsafe import Markup

from odoo import http, tools
from odoo.http import request


class DigitalBusinessCardSite(http.Controller):
    """Public-facing digital business cards.

    Each published card has a permanent link at /card/<access_token> — the token
    is a random, unguessable hash so cards can't be enumerated. The page is
    public (auth='public'); records are read with sudo() because anonymous
    visitors have no access rights of their own.
    """

    def _get_card(self, token):
        # Only PUBLISHED cards are reachable — draft/deactivated ones 404.
        if not token:
            return request.env['digital.business.card']
        return request.env['digital.business.card'].sudo().search(
            [('access_token', '=', token), ('active', '=', True),
             ('state', '=', 'published')], limit=1)

    def _safe_design(self, card):
        """The custom design is stored RAW (so the builder stays re-editable),
        so it MUST be sanitized here before it reaches a public browser —
        scripts/js are stripped while layout (styles/classes) is kept."""
        design = card.source_html_inline or card.source_html
        if not design:
            return False
        return Markup(tools.html_sanitize(
            design, sanitize_tags=True, strip_style=False, strip_classes=False))

    @http.route('/card/<string:token>', type='http', auth='public', website=False)
    def card_page(self, token, **kw):
        card = self._get_card(token)
        if not card:
            return request.not_found()
        return request.render('digital_business_card.card_public_page',
                              {'card': card, 'design_html': self._safe_design(card)})

    @http.route('/card/<string:token>/vcard', type='http', auth='public', website=False)
    def card_vcard(self, token, **kw):
        """Download the contact as a .vcf file (Import to contact)."""
        card = self._get_card(token)
        if not card:
            return request.not_found()
        vcf = card._build_vcard()
        return request.make_response(vcf, headers=[
            ('Content-Type', 'text/vcard; charset=utf-8'),
            ('Content-Disposition',
             'attachment; filename="%s.vcf"' % (card.slug or 'contact')),
        ])

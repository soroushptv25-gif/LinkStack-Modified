# Part of the Digital Business Card module.
from odoo import http
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

    @http.route('/card/<string:token>', type='http', auth='public', website=False)
    def card_page(self, token, **kw):
        card = self._get_card(token)
        if not card:
            return request.not_found()
        return request.render(
            'digital_business_card.card_public_page', {'card': card})

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

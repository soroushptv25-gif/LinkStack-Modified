# Part of the Digital Business Card module.
from odoo import http
from odoo.http import request


class DigitalBusinessCardSite(http.Controller):
    """Public-facing digital business cards.

    Each card has a permanent link at /card/<slug>. The page is public
    (auth='public') so the card can be opened by anyone with the URL or by
    scanning its QR code. Records are read with sudo() because anonymous
    visitors have no access rights of their own.
    """

    def _get_card(self, slug):
        return request.env['digital.business.card'].sudo().search(
            [('slug', '=', slug), ('active', '=', True)], limit=1)

    @http.route('/card/<string:slug>', type='http', auth='public', website=False)
    def card_page(self, slug, **kw):
        card = self._get_card(slug)
        if not card:
            return request.not_found()
        return request.render(
            'digital_business_card.card_public_page', {'card': card})

    @http.route('/card/<string:slug>/vcard', type='http', auth='public', website=False)
    def card_vcard(self, slug, **kw):
        """Download the contact as a .vcf file (Import to contact)."""
        card = self._get_card(slug)
        if not card:
            return request.not_found()
        vcf = card._build_vcard()
        return request.make_response(vcf, headers=[
            ('Content-Type', 'text/vcard; charset=utf-8'),
            ('Content-Disposition',
             'attachment; filename="%s.vcf"' % (card.slug or 'contact')),
        ])

# Part of the Digital Business Card module.
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Both are backed by system parameters (config_parameter=), so Odoo reads
    # and writes them automatically — no get_values/set_values needed.
    dbc_employee_email_field = fields.Selection(
        [('work_email', 'Work Email'), ('private_email', 'Private Email')],
        string='Card Email Source', default='work_email',
        config_parameter='digital_business_card.employee_email_field',
        help="Which employee email a card shows by default. A per-card Email "
             "mask still overrides this on individual cards.")
    dbc_default_template = fields.Selection(
        [('classic', 'Classic'), ('dark', 'Dark'), ('minimal', 'Minimal')],
        string='Default Public Page Design', default='classic',
        config_parameter='digital_business_card.default_template',
        help="Design applied to new cards' public pages. Each card can still "
             "pick its own design.")

    # --- Publishing ---------------------------------------------------------
    # Base web address that prefixes every published card's link and QR code.
    # Empty = use Odoo's own web.base.url (see _compute_public_url).
    dbc_public_base_url = fields.Char(
        string='Publishing Address',
        config_parameter='digital_business_card.public_base_url',
        help="Base web address used in every published card's link and QR "
             "code, e.g. https://cards.example.com. Leave empty to use Odoo's "
             "own base URL. Useful when cards are served under a custom domain "
             "or reverse proxy.")

    # Read-only count of configured Publish Targets (external hosts cards are
    # sent to). Not a stored setting — just a live figure for the Settings page.
    dbc_target_count = fields.Integer(
        string='Publish Targets', compute='_compute_dbc_target_count')

    @api.depends_context('uid')
    def _compute_dbc_target_count(self):
        count = self.env['digital.business.card.target'].search_count([])
        for setting in self:
            setting.dbc_target_count = count

    def action_open_dbc_targets(self):
        """Open the Publish Targets list from the Settings page."""
        return self.env['ir.actions.act_window']._for_xml_id(
            'digital_business_card.action_dbc_target')

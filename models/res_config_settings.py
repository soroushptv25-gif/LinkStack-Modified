# Part of the Digital Business Card module.
from odoo import fields, models


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

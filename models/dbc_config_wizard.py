# Part of the Digital Business Card module.
from odoo import api, fields, models

# System parameter: 'true' = auto-generate a card per employee, anything else
# (default) = manual.
AUTO_PARAM = 'digital_business_card.auto_generate'


class DigitalBusinessCardConfigWizard(models.TransientModel):
    _name = 'digital.business.card.config.wizard'
    _description = 'Business Card Generation Settings'

    auto_generate = fields.Boolean(
        string='Automatically generate employee cards',
        help="On: every employee gets a business card automatically. "
             "Off (default): you create cards manually.")
    apply_scope = fields.Selection(
        [('future', 'Only future employees'),
         ('all', 'All existing employees now (and future)')],
        string='Generate for', default='future',
        help="When turning automatic generation on, choose whether to also "
             "create cards for the employees already in the system.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['auto_generate'] = self._auto_enabled()
        return res

    @api.model
    def _auto_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param(AUTO_PARAM) == 'true'

    def action_apply(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            AUTO_PARAM, 'true' if self.auto_generate else 'false')
        created = 0
        if self.auto_generate and self.apply_scope == 'all':
            employees = self.env['hr.employee'].sudo().search([])
            cards = self.env['digital.business.card'].sudo().create_for_employees(employees)
            cards.action_generate()
            created = len(cards)
        if self.auto_generate:
            message = 'Automatic generation is ON.'
            if created:
                message += ' %s employee card(s) are now in place.' % created
        else:
            message = 'Manual mode — no cards are auto-generated.'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Card Generation', 'message': message,
                       'type': 'success', 'sticky': False},
        }

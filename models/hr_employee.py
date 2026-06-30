# Part of the Digital Business Card module.
from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        # Auto-create a card per employee only when automatic generation is
        # turned on (default is manual). Done with sudo() so creating an
        # employee never fails on card access rules, and so the card can be
        # owned by the employee's own user.
        auto = self.env['ir.config_parameter'].sudo().get_param(
            'digital_business_card.auto_generate')
        if auto == 'true':
            self.env['digital.business.card'].sudo().create_for_employees(employees)
        return employees

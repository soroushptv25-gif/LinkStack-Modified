# Part of the Digital Business Card module.
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    business_card_ids = fields.One2many(
        'digital.business.card', 'employee_id', string='Business Cards')

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        # Every employee gets a name-only placeholder card so they appear in the
        # Cards list right away. Done with sudo() so creating an employee never
        # fails on card access rules, and so the card is owned by the employee.
        cards = self.env['digital.business.card'].sudo().create_for_employees(employees)
        # When automatic generation is on, also publish (link + QR live) now.
        auto = self.env['ir.config_parameter'].sudo().get_param(
            'digital_business_card.auto_generate')
        if auto == 'true':
            cards.action_publish()
        return employees

# Part of the Digital Business Card module.
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    business_card_ids = fields.One2many(
        'digital.business.card', 'employee_id', string='Business Cards')

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        # Every employee gets a name-only Draft card so they appear in the Cards
        # list right away. Publishing (link + QR) is a deliberate workflow step:
        # the Publish button on the card, or Employees > Actions > Create
        # Business Card (which creates and publishes in one go).
        # sudo() so creating an employee never fails on card access rules, and
        # so the card is owned by the employee's own user.
        self.env['digital.business.card'].sudo().create_for_employees(employees)
        return employees

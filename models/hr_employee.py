# Part of the Digital Business Card module.
from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        # Every new employee automatically gets a public business card. Done
        # with sudo() so creating an employee never fails on card access rules,
        # and so the card can be owned by the employee's own user.
        self.env['digital.business.card'].sudo().create_for_employees(employees)
        return employees

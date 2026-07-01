# Part of the Digital Business Card module.
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    business_card_ids = fields.One2many(
        'digital.business.card', 'employee_id', string='Business Cards')
    # Stored so it can be filtered efficiently ("employees without a card").
    # Computed with sudo() so it is correct no matter who owns the card
    # (regular users only see their own cards through the record rules).
    has_business_card = fields.Boolean(
        string='Has Business Card', compute='_compute_has_business_card', store=True)

    @api.depends('business_card_ids')
    def _compute_has_business_card(self):
        Card = self.env['digital.business.card'].sudo()
        for employee in self:
            employee.has_business_card = bool(
                Card.search_count([('employee_id', '=', employee.id)])) if employee.id else False

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

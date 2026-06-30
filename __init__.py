from . import models
from . import controllers


def post_init_hook(env):
    """Backfill: give every existing employee a public business card."""
    env['digital.business.card'].sudo().create_for_employees(
        env['hr.employee'].sudo().search([]))

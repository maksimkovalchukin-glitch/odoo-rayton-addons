from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'
    # tg_user_id — temporarily absent (step 1 of 2-step DB migration)
    # Will be re-added after a successful module upgrade.

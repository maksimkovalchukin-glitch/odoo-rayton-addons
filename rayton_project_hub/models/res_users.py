from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # tg_user_id is defined here but removed temporarily.
    # After a successful module upgrade (to clear the broken DB state),
    # re-add:  tg_user_id = fields.Char(string='Telegram User ID', ...)
    # and upgrade again so Odoo creates the column in PostgreSQL.

from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    tg_user_id = fields.Char(
        string='Telegram User ID',
        help='Числовий ID користувача в Telegram (не username). '
             'Отримати можна через бота @userinfobot — надішліть йому /start.',
    )

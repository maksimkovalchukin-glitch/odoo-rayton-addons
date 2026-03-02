from odoo import models, fields


class RaytonTgUserMapping(models.Model):
    _name = 'rayton.tg.user.mapping'
    _description = 'Маппінг: Telegram ↔ Odoo користувач'
    _rec_name = 'telegram_username'
    _order = 'telegram_username'

    telegram_username = fields.Char(
        string='Telegram @username',
        required=True,
        index=True,
        help='Нікнейм в Telegram без @. Напр.: irynabakumenko',
    )
    odoo_user_id = fields.Many2one(
        'res.users',
        string='Odoo користувач',
        required=True,
        ondelete='cascade',
    )
    api_token = fields.Char(
        string='API токен',
        help='Токен Odoo API для цього користувача (використовується n8n для надсилання повідомлень від його імені).',
    )

    _sql_constraints = [
        ('unique_telegram_username', 'UNIQUE(telegram_username)',
         'Цей Telegram username вже є в маппінгу!'),
    ]

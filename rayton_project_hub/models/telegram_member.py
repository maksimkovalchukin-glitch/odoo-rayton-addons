from odoo import models, fields, api


class RaytonTelegramMember(models.Model):
    _name = 'rayton.telegram.member'
    _description = 'Учасники Telegram груп'
    _order = 'role asc, name asc'

    name = fields.Char(string='Ім\'я', required=True)
    username = fields.Char(
        string='Telegram нік',
        required=True,
        help='Нікнейм з @ або без (напр. @ivan_manager або ivan_manager)',
    )
    role = fields.Selection(
        selection=[
            ('mandatory', 'Обов\'язковий'),
            ('optional', 'Необов\'язковий'),
        ],
        string='Роль',
        default='mandatory',
        required=True,
        help='Обов\'язкові автоматично підтягуються у wizard створення групи.',
    )

    _sql_constraints = [
        ('username_unique', 'UNIQUE(username)', 'Такий нікнейм вже додано!'),
    ]

    @api.model
    def action_open_create_wizard(self):
        """Open the 'Create TG Group' wizard (pre-fills mandatory members)."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Створити Telegram групу',
            'res_model': 'rayton.telegram.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {},
        }

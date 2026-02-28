import logging
from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RaytonTelegramChat(models.Model):
    _name = 'rayton.telegram.chat'
    _description = 'Пул Telegram груп'
    _order = 'state asc, name asc'

    name = fields.Char(
        string='Назва групи',
        required=True,
    )
    tg_chat_id = fields.Char(
        string='ID Telegram чату',
        required=True,
        help='Від\'ємне число (напр. -1003883870898)',
    )
    state = fields.Selection(
        selection=[
            ('free', 'Вільна'),
            ('busy', 'Зайнята'),
        ],
        string='Статус',
        default='free',
        required=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='Проект',
        readonly=True,
        ondelete='set null',
    )
    discuss_channel_id = fields.Many2one(
        'discuss.channel',
        string='Канал Discuss',
        readonly=True,
        ondelete='set null',
    )

    _sql_constraints = [
        ('tg_chat_id_unique', 'UNIQUE(tg_chat_id)',
         'Цей Telegram чат вже доданий до пулу!'),
    ]

    def action_release(self):
        """Звільнити групу — повернути до пулу вільних."""
        for rec in self:
            rec.write({
                'state': 'free',
                'project_id': False,
                'discuss_channel_id': False,
            })
        return True

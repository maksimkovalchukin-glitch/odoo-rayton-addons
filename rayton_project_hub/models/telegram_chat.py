import logging
import requests
from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TG_API = 'https://api.telegram.org/bot{token}/{method}'


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

    def add_admin_to_chat(self, tg_user_id, token):
        """
        Add a user to the Telegram group and promote them to administrator.

        Steps:
          1. unbanChatMember  — allows the user to join even if previously removed
          2. addChatMember    — adds them to the group
          3. promoteChatMember — grants admin rights (without ability to add other admins)

        Requires the bot to be an admin of the group with 'can_invite_users'
        and 'can_promote_members' permissions.
        """
        self.ensure_one()
        if not tg_user_id or not token:
            _logger.warning("[RaytonTG] add_admin_to_chat: missing tg_user_id or token")
            return

        chat_id = self.tg_chat_id
        user_id = int(tg_user_id)

        def _call(method, payload):
            url = TG_API.format(token=token, method=method)
            try:
                resp = requests.post(url, json=payload, timeout=10)
                data = resp.json()
                if not data.get('ok'):
                    _logger.warning(
                        "[RaytonTG] %s failed: %s", method, data.get('description', '')
                    )
                else:
                    _logger.info("[RaytonTG] %s OK for user %s in chat %s", method, user_id, chat_id)
                return data
            except Exception as e:
                _logger.warning("[RaytonTG] %s error: %s", method, str(e))
                return {}

        # 1. Unban (allows re-join if previously removed)
        _call('unbanChatMember', {
            'chat_id': chat_id,
            'user_id': user_id,
            'only_if_banned': True,
        })

        # 2. Add to group
        _call('addChatMember', {
            'chat_id': chat_id,
            'user_id': user_id,
        })

        # 3. Promote to admin
        _call('promoteChatMember', {
            'chat_id': chat_id,
            'user_id': user_id,
            'can_manage_chat': True,
            'can_change_info': True,
            'can_delete_messages': True,
            'can_invite_users': True,
            'can_pin_messages': True,
            'can_manage_video_chats': True,
            'can_promote_members': False,   # не може додавати інших адмінів
            'can_restrict_members': False,
        })

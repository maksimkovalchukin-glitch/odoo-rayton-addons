import logging
import time

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

    def action_promote_manager_to_admin(self):
        """
        Promote the linked project's manager to TG group admin.
        Call this AFTER the manager has joined the group via the invite link.
        """
        self.ensure_one()
        token = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_bot_token', ''
        )
        if not token:
            raise UserError(_('Telegram bot token не налаштовано (Налаштування → Системні параметри).'))

        manager = self.project_id.user_id if self.project_id else None
        if not manager:
            raise UserError(_('До цієї TG групи не прив\'язано проект або менеджера.'))

        tg_user_id = getattr(manager, 'tg_user_id', '') or ''
        if not tg_user_id:
            raise UserError(_(
                'У менеджера %s не вказано Telegram User ID.\n'
                'Додайте його у Налаштування → Користувачі → %s → поле "Telegram User ID".'
            ) % (manager.name, manager.name))

        self.promote_to_admin(tg_user_id, token)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Готово',
                'message': f'{manager.name} призначено адміністратором TG групи.',
                'type': 'success',
            },
        }

    def create_invite_link(self, token):
        """
        Create a one-time invite link for this Telegram group (valid 7 days).

        Note: Telegram Bot API does NOT have addChatMember — bots cannot
        forcefully add users. The correct approach is to generate a personal
        invite link and show it to the initiator so they can join themselves.
        Once they join, promote_to_admin() can be called separately.
        """
        self.ensure_one()
        if not token:
            return None
        url = TG_API.format(token=token, method='createChatInviteLink')
        try:
            resp = requests.post(url, json={
                'chat_id': self.tg_chat_id,
                'member_limit': 1,
                'expire_date': int(time.time()) + 7 * 24 * 3600,  # 7 days
            }, timeout=10)
            data = resp.json()
            if data.get('ok'):
                link = data['result']['invite_link']
                _logger.info("[RaytonTG] Invite link created for chat %s", self.tg_chat_id)
                return link
            else:
                _logger.warning(
                    "[RaytonTG] createChatInviteLink failed: %s", data.get('description', '')
                )
        except Exception as e:
            _logger.warning("[RaytonTG] createChatInviteLink error: %s", str(e))
        return None

    def promote_to_admin(self, tg_user_id, token):
        """
        Promote an already-joined user to administrator.
        Call this only after the user has joined the group via invite link.
        """
        self.ensure_one()
        if not tg_user_id or not token:
            return
        url = TG_API.format(token=token, method='promoteChatMember')
        try:
            resp = requests.post(url, json={
                'chat_id': self.tg_chat_id,
                'user_id': int(tg_user_id),
                'can_manage_chat': True,
                'can_change_info': True,
                'can_delete_messages': True,
                'can_invite_users': True,
                'can_pin_messages': True,
                'can_manage_video_chats': True,
                'can_promote_members': False,
                'can_restrict_members': False,
            }, timeout=10)
            data = resp.json()
            if data.get('ok'):
                _logger.info("[RaytonTG] promoteChatMember OK for user %s", tg_user_id)
            else:
                _logger.warning(
                    "[RaytonTG] promoteChatMember failed: %s", data.get('description', '')
                )
        except Exception as e:
            _logger.warning("[RaytonTG] promoteChatMember error: %s", str(e))

    def send_dm(self, tg_user_id, text, token):
        """Send a direct message to a Telegram user (requires user to have started the bot first)."""
        self.ensure_one()
        if not tg_user_id or not token:
            return
        url = TG_API.format(token=token, method='sendMessage')
        try:
            resp = requests.post(url, json={
                'chat_id': int(tg_user_id),
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            }, timeout=10)
            data = resp.json()
            if not data.get('ok'):
                _logger.warning("[RaytonTG] sendMessage (DM) failed: %s", data.get('description', ''))
            else:
                _logger.info("[RaytonTG] DM sent to user %s", tg_user_id)
        except Exception as e:
            _logger.warning("[RaytonTG] sendMessage (DM) error: %s", str(e))

    def rename_chat(self, new_title, token):
        """Rename the Telegram group to match the project name."""
        self.ensure_one()
        if not new_title or not token:
            return
        url = TG_API.format(token=token, method='setChatTitle')
        try:
            resp = requests.post(url, json={
                'chat_id': self.tg_chat_id,
                'title': new_title,
            }, timeout=10)
            data = resp.json()
            if not data.get('ok'):
                _logger.warning(
                    "[RaytonTG] setChatTitle failed: %s", data.get('description', '')
                )
            else:
                _logger.info("[RaytonTG] Renamed TG chat to '%s'", new_title)
        except Exception as e:
            _logger.warning("[RaytonTG] setChatTitle error: %s", str(e))

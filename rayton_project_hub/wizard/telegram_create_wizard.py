import logging

import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RaytonTelegramCreateWizard(models.TransientModel):
    _name = 'rayton.telegram.create.wizard'
    _description = 'Wizard: Створення Telegram групи'

    title = fields.Char(string='Назва групи', required=True)
    member_ids = fields.Many2many(
        'rayton.telegram.member',
        string='Учасники',
        help='Будуть запрошені в групу через Telethon.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'member_ids' in fields_list:
            mandatory = self.env['rayton.telegram.member'].search([('role', '=', 'mandatory')])
            res['member_ids'] = [(6, 0, mandatory.ids)]
        return res

    def action_create(self):
        """Create Telegram supergroup via Telethon, add members, save to pool."""
        self.ensure_one()

        service_url = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_service_url', ''
        )
        service_secret = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_service_secret', ''
        )
        if not service_url or not service_secret:
            raise UserError(_(
                'Telethon-сервіс не налаштовано.\n'
                'Додайте системні параметри:\n'
                '  rayton_project_hub.tg_service_url\n'
                '  rayton_project_hub.tg_service_secret'
            ))

        def _norm(u):
            return u if u.startswith('@') else f'@{u}'

        usernames = [_norm(m.username) for m in self.member_ids if m.username]
        admin_usernames = [_norm(m.username) for m in self.member_ids if m.username and m.is_admin]

        try:
            resp = requests.post(
                f'{service_url.rstrip("/")}/create_group',
                json={
                    'title': self.title,
                    'usernames': usernames,
                    'admin_usernames': admin_usernames,
                },
                headers={'x-secret': service_secret},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise UserError(_('Помилка виклику Telethon-сервісу: %s') % str(e))

        if data.get('status') != 'ok':
            raise UserError(_('Сервіс повернув помилку: %s') % data.get('detail', str(data)))

        chat_id = data['chat_id']
        actual_title = data.get('title', self.title)

        self.env['rayton.telegram.chat'].create({
            'name': actual_title,
            'tg_chat_id': chat_id,
            'state': 'free',
        })
        _logger.info("[RaytonTG] Pool group created via wizard: %s (%s)", actual_title, chat_id)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Групу створено!',
                'message': f'Telegram-група "{actual_title}" ({chat_id}) додана до пулу.',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

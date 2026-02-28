import logging
import requests
from odoo import models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

TG_API = 'https://api.telegram.org/bot{token}/sendMessage'


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def message_post(self, **kwargs):
        msg = super().message_post(**kwargs)
        if msg and not self.env.context.get('tg_no_forward'):
            self.sudo()._rayton_forward_to_tg(msg)
        return msg

    def _rayton_forward_to_tg(self, message):
        """Forward an Odoo Discuss message to the linked Telegram group via bot."""
        # Only forward regular user comments, not system notifications
        if message.message_type not in ('comment',):
            return

        # Skip OdooBot (partner_root) — system messages
        bot_partner = self.env.ref('base.partner_root', raise_if_not_found=False)
        if bot_partner and message.author_id.id == bot_partner.id:
            return

        # Find the linked Telegram chat for this channel
        tg_chat = self.env['rayton.telegram.chat'].search([
            ('discuss_channel_id', '=', self.id),
            ('state', '=', 'busy'),
        ], limit=1)
        if not tg_chat:
            return

        token = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_bot_token'
        )
        if not token:
            _logger.warning(
                "[RaytonProjectHub] TG bot token not configured — message not forwarded."
            )
            return

        # Build plain-text body from HTML
        body_text = html2plaintext(message.body or '').strip()
        if not body_text:
            return

        author_name = message.author_id.name or 'Хтось'
        text = f'💬 <b>{author_name}</b> (Odoo):\n{body_text}'

        try:
            resp = requests.post(
                TG_API.format(token=token),
                json={
                    'chat_id': tg_chat.tg_chat_id,
                    'text': text,
                    'parse_mode': 'HTML',
                },
                timeout=10,
            )
            if resp.status_code != 200:
                _logger.warning(
                    "[RaytonProjectHub] TG sendMessage failed: %s %s",
                    resp.status_code, resp.text[:200],
                )
        except Exception as e:
            _logger.warning("[RaytonProjectHub] TG sendMessage error: %s", str(e))

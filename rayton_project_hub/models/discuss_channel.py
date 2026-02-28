import base64
import logging
import requests
from odoo import models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

TG_BASE = 'https://api.telegram.org/bot{token}/{method}'

# TG caption max length
TG_CAPTION_LIMIT = 1024


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def message_post(self, **kwargs):
        msg = super().message_post(**kwargs)
        if msg and not self.env.context.get('tg_no_forward'):
            self.sudo()._rayton_forward_to_tg(msg)
        return msg

    def _rayton_forward_to_tg(self, message):
        """Forward an Odoo Discuss message (text + attachments) to the linked TG group."""
        # Only forward regular user comments, not system notifications
        if message.message_type not in ('comment',):
            return

        # Skip OdooBot (system)
        bot_partner = self.env.ref('base.partner_root', raise_if_not_found=False)
        if bot_partner and message.author_id.id == bot_partner.id:
            return

        # Find linked TG chat
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
            _logger.warning("[RaytonTG] Bot token not configured — message not forwarded.")
            return

        chat_id = tg_chat.tg_chat_id
        author_name = message.author_id.name or 'Хтось'
        body_text = html2plaintext(message.body or '').strip()
        attachments = message.attachment_ids

        if attachments:
            # Send each attachment; first one gets the text as caption
            for idx, attachment in enumerate(attachments):
                caption = None
                if idx == 0:
                    header = f'💬 <b>{author_name}</b> (Odoo):'
                    if body_text:
                        full = f'{header}\n{body_text}'
                    else:
                        full = header
                    caption = full[:TG_CAPTION_LIMIT]
                self._rayton_send_attachment(token, chat_id, attachment, caption)
        elif body_text:
            # Text-only message
            text = f'💬 <b>{author_name}</b> (Odoo):\n{body_text}'
            self._rayton_tg_call(
                token, 'sendMessage',
                json_data={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            )

    def _rayton_send_attachment(self, token, chat_id, attachment, caption):
        """Send a single attachment to TG using the appropriate method."""
        raw = attachment.datas
        if not raw:
            return
        try:
            file_bytes = base64.b64decode(raw)
        except Exception:
            _logger.warning("[RaytonTG] Failed to decode attachment '%s'", attachment.name)
            return

        mimetype = (attachment.mimetype or '').lower()
        filename = attachment.name or 'file'

        # Choose TG send method and multipart field name
        if mimetype.startswith('image/') and mimetype not in ('image/webp', 'image/gif'):
            method, field = 'sendPhoto', 'photo'
        elif mimetype.startswith('video/'):
            method, field = 'sendVideo', 'video'
        elif mimetype == 'audio/ogg':
            method, field = 'sendVoice', 'voice'
        elif mimetype.startswith('audio/'):
            method, field = 'sendAudio', 'audio'
        else:
            method, field = 'sendDocument', 'document'

        form_data = {'chat_id': chat_id}
        if caption:
            form_data['caption'] = caption
            form_data['parse_mode'] = 'HTML'

        self._rayton_tg_call(
            token, method,
            form_data=form_data,
            files={field: (filename, file_bytes, mimetype)},
        )

    def _rayton_tg_call(self, token, method, json_data=None, form_data=None, files=None):
        """Low-level TG API call with error logging."""
        url = TG_BASE.format(token=token, method=method)
        try:
            if files:
                resp = requests.post(url, data=form_data, files=files, timeout=30)
            else:
                resp = requests.post(url, json=json_data, timeout=10)

            if resp.status_code != 200:
                _logger.warning(
                    "[RaytonTG] %s failed: %s %s",
                    method, resp.status_code, resp.text[:300],
                )
            else:
                _logger.debug("[RaytonTG] %s OK", method)
        except Exception as e:
            _logger.warning("[RaytonTG] %s error: %s", method, str(e))

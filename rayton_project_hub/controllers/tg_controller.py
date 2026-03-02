"""
Controllers: Telegram ↔ Odoo integration

/rayton/tg/webhook — Direct Telegram Bot API webhook (replaces n8n).
    Receives updates from Telegram, looks up user + channel mapping,
    posts to Odoo Discuss as the correct user. Set webhook via:
      POST https://api.telegram.org/bot{TOKEN}/setWebhook
      {"url": "https://2xqjwr7pzvj.cloudpepper.site/rayton/tg/webhook",
       "secret_token": "<rayton_project_hub.tg_webhook_secret>",
       "allowed_updates": ["message", "edited_message"]}

/rayton/tg/post — Legacy n8n endpoint (kept for backward compatibility).
/rayton/tg/promote — Called by n8n on new member join (promote to admin).
"""
import json
import logging
from markupsafe import Markup, escape
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RaytonTgController(http.Controller):

    # ──────────────────────────────────────────────────────────────────────────
    # Direct Telegram webhook — replaces n8n for TG→Odoo direction
    # ──────────────────────────────────────────────────────────────────────────

    @http.route(
        '/rayton/tg/webhook',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def tg_webhook(self, **kwargs):
        """
        Telegram Bot API webhook handler.
        Receives raw JSON update, maps TG user + chat to Odoo, posts to Discuss.
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response('Bad Request', status=400)

        # Verify secret token (set via rayton_project_hub.tg_webhook_secret)
        secret = request.httprequest.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        expected = request.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_webhook_secret', ''
        )
        if expected and secret != expected:
            _logger.warning("[TG Webhook] Invalid secret token")
            return request.make_response('Unauthorized', status=401)

        message = data.get('message') or data.get('edited_message')
        if not message:
            return request.make_response('ok')

        from_data = message.get('from', {})
        if from_data.get('is_bot'):
            return request.make_response('ok')

        chat_id = str(message.get('chat', {}).get('id', ''))
        if not chat_id:
            return request.make_response('ok')

        # Build text content
        text = message.get('text') or message.get('caption') or ''
        if not text:
            if 'photo' in message:
                text = '[📷 Фото]'
            elif 'video' in message:
                text = '[🎥 Відео]'
            elif 'voice' in message:
                text = '[🎤 Голосове]'
            elif 'document' in message:
                text = f"[📎 {message['document'].get('file_name', 'Файл')}]"
            elif 'sticker' in message:
                text = f"[{message['sticker'].get('emoji', '🎭')} Стікер]"
            else:
                return request.make_response('ok')

        username = from_data.get('username', '')
        first_name = from_data.get('first_name', '')
        last_name = from_data.get('last_name', '')

        env = request.env

        # Find linked Discuss channel
        tg_chat = env['rayton.telegram.chat'].sudo().search(
            [('tg_chat_id', '=', chat_id)], limit=1
        )
        if not tg_chat or not tg_chat.discuss_channel_id:
            return request.make_response('ok')

        channel = tg_chat.discuss_channel_id

        # Look up Odoo user by TG username
        author_partner = None
        if username:
            mapping = env['rayton.tg.user.mapping'].sudo().search(
                [('telegram_username', '=', username)], limit=1
            )
            if mapping and mapping.odoo_user_id:
                author_partner = mapping.odoo_user_id.partner_id

        if author_partner:
            body = Markup('<p>{}</p>').format(escape(text))
        else:
            sender_name = f"{first_name} {last_name}".strip() or username or 'TG'
            body = Markup('<p>📱 <b>{}</b>: {}</p>').format(
                escape(sender_name), escape(text)
            )

        channel.sudo().with_context(tg_no_forward=True).message_post(
            body=body,
            author_id=author_partner.id if author_partner else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return request.make_response('ok')

    # ──────────────────────────────────────────────────────────────────────────
    # Legacy n8n endpoints (kept for backward compatibility)
    # ──────────────────────────────────────────────────────────────────────────

    @http.route(
        '/rayton/tg/post',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def tg_post(self, **kwargs):
        # ── Auth: verify api_key matches the stored bot token ────────────────
        provided_key = kwargs.get('api_key', '')
        stored_token = request.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_bot_token', ''
        )
        if not stored_token or provided_key != stored_token:
            _logger.warning("[RaytonTg] /rayton/tg/post — invalid api_key")
            return {'status': 'error', 'message': 'Unauthorized'}

        tg_chat_id = str(kwargs.get('tg_chat_id', '')).strip()
        body = kwargs.get('body', '').strip()
        from_name = kwargs.get('from_name', '').strip()

        if not tg_chat_id or not body:
            return {'status': 'error', 'message': 'tg_chat_id and body are required'}

        # ── Find channel by tg_chat_id ────────────────────────────────────────
        tg_chat = request.env['rayton.telegram.chat'].sudo().search([
            ('tg_chat_id', '=', tg_chat_id),
        ], limit=1)

        if not tg_chat or not tg_chat.discuss_channel_id:
            _logger.warning(
                "[RaytonTg] No Odoo channel linked to tg_chat_id=%s", tg_chat_id
            )
            return {'status': 'error', 'message': 'Chat mapping not found'}

        # ── Build message body ────────────────────────────────────────────────
        safe_name = escape(from_name) if from_name else 'TG'
        safe_body = escape(body)
        msg_body = Markup(f'<b>{safe_name}</b>: {safe_body}')

        # ── Post with no_forward context (prevents re-sending back to TG) ─────
        tg_chat.discuss_channel_id.sudo().with_context(tg_no_forward=True).message_post(
            body=msg_body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return {'status': 'ok'}

    @http.route(
        '/rayton/tg/promote',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def tg_promote(self, **kwargs):
        """
        Called by n8n when a new member joins a TG group.
        Promotes them to admin if they are the project initiator.

        Expected payload:
          {
            "api_key":    "<bot_token>",
            "tg_chat_id": "-1003883870898",
            "tg_user_id": "123456789"
          }
        """
        provided_key = kwargs.get('api_key', '')
        stored_token = request.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_bot_token', ''
        )
        if not stored_token or provided_key != stored_token:
            _logger.warning("[RaytonTg] /rayton/tg/promote — invalid api_key")
            return {'status': 'error', 'message': 'Unauthorized'}

        tg_chat_id = str(kwargs.get('tg_chat_id', '')).strip()
        tg_user_id = str(kwargs.get('tg_user_id', '')).strip()

        if not tg_chat_id or not tg_user_id:
            return {'status': 'error', 'message': 'tg_chat_id and tg_user_id are required'}

        tg_chat = request.env['rayton.telegram.chat'].sudo().search([
            ('tg_chat_id', '=', tg_chat_id),
            ('state', '=', 'busy'),
        ], limit=1)
        if not tg_chat:
            return {'status': 'error', 'message': 'Chat not found or not busy'}

        # Promote the user
        tg_chat.promote_to_admin(tg_user_id, stored_token)
        _logger.info(
            "[RaytonTg] Promoted user %s to admin in chat %s (via n8n webhook)",
            tg_user_id, tg_chat_id,
        )
        return {'status': 'ok'}

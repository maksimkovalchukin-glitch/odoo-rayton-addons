"""
Controller: TG → Odoo message post

Endpoint: POST /rayton/tg/post
Purpose:  Receives a Telegram message from n8n and posts it to the linked
          Discuss channel with tg_no_forward=True to prevent loop.

This endpoint replaces the direct JSONRPC call to discuss.channel.message_post
that n8n currently performs via the Google Sheets mapping.

Expected JSON payload:
  {
    "tg_chat_id":   "-1003883870898",   # Telegram group chat ID (string)
    "body":         "Привіт!",          # Plain text or simple HTML
    "from_name":    "Юрій Лисенко",    # Display name for the author label
    "api_key":      "<token>"           # Must match rayton_project_hub.tg_bot_token
  }
"""
import logging
from markupsafe import Markup, escape
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RaytonTgController(http.Controller):

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

"""
Controllers: Telegram ↔ Odoo integration

/rayton/tg/webhook — Direct Telegram Bot API webhook (replaces n8n).
    Receives updates from Telegram, looks up user + channel mapping,
    posts to Odoo Discuss as the correct user. Media files (photo, voice,
    document) are downloaded and attached; large video — placeholder.
    Set webhook via:
      POST https://api.telegram.org/bot{TOKEN}/setWebhook
      {"url": "https://2xqjwr7pzvj.cloudpepper.site/rayton/tg/webhook",
       "secret_token": "<rayton_project_hub.tg_webhook_secret>",
       "allowed_updates": ["message", "edited_message"]}

/rayton/tg/post — Legacy n8n endpoint (kept for backward compatibility).
/rayton/tg/promote — Called by n8n on new member join (promote to admin).
"""
import base64
import json
import logging
from markupsafe import Markup, escape

import requests as _requests
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

TG_API = 'https://api.telegram.org/bot{token}/{method}'
TG_FILE = 'https://api.telegram.org/file/bot{token}/{path}'
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # 20 MB — skip larger files


def _tg_download(token, file_id):
    """
    Download a file from Telegram. Returns (bytes, filename, mimetype) or None.
    Skips files larger than MAX_DOWNLOAD_BYTES.
    """
    try:
        resp = _requests.get(
            TG_API.format(token=token, method='getFile'),
            params={'file_id': file_id},
            timeout=10,
        )
        data = resp.json()
        if not data.get('ok'):
            return None
        file_obj = data['result']
        file_size = file_obj.get('file_size', 0)
        if file_size and file_size > MAX_DOWNLOAD_BYTES:
            return None
        file_path = file_obj['file_path']
        dl = _requests.get(
            TG_FILE.format(token=token, path=file_path),
            timeout=30,
        )
        if dl.status_code != 200:
            return None
        # Guess filename and mimetype from path
        name = file_path.rsplit('/', 1)[-1]
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        mime_map = {
            'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
            'gif': 'image/gif', 'webp': 'image/webp',
            'ogg': 'audio/ogg', 'oga': 'audio/ogg', 'mp3': 'audio/mpeg',
            'mp4': 'video/mp4', 'mov': 'video/quicktime',
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
        mimetype = mime_map.get(ext, 'application/octet-stream')
        return dl.content, name, mimetype
    except Exception as e:
        _logger.warning("[TG Webhook] _tg_download error: %s", e)
        return None


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
        - Text messages → post as the mapped Odoo user
        - Photo / voice / document → download & attach to the Discuss message
        - Video (potentially huge) → placeholder text
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response('Bad Request', status=400)

        # ── Verify secret token ───────────────────────────────────────────────
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

        env = request.env

        # ── Find linked Discuss channel ───────────────────────────────────────
        tg_chat = env['rayton.telegram.chat'].sudo().search(
            [('tg_chat_id', '=', chat_id)], limit=1
        )
        if not tg_chat or not tg_chat.discuss_channel_id:
            return request.make_response('ok')

        channel = tg_chat.discuss_channel_id

        # ── Resolve Odoo author ───────────────────────────────────────────────
        username = from_data.get('username', '')
        first_name = from_data.get('first_name', '')
        last_name = from_data.get('last_name', '')

        author_partner = None
        if username:
            mapping = env['rayton.tg.user.mapping'].sudo().search(
                [('telegram_username', '=', username)], limit=1
            )
            if mapping and mapping.odoo_user_id:
                author_partner = mapping.odoo_user_id.partner_id

        # ── Determine content: text + optional file ───────────────────────────
        token = env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_bot_token', ''
        )

        text = message.get('text') or message.get('caption') or ''
        file_id = None
        filename = None
        mimetype = None

        if 'photo' in message:
            # Pick the highest-resolution photo
            photos = message['photo']
            best = max(photos, key=lambda p: p.get('file_size', 0))
            file_id = best['file_id']
            filename = 'photo.jpg'
            mimetype = 'image/jpeg'

        elif 'voice' in message:
            v = message['voice']
            file_id = v['file_id']
            filename = 'voice.ogg'
            mimetype = 'audio/ogg'

        elif 'audio' in message:
            a = message['audio']
            file_id = a['file_id']
            filename = a.get('file_name') or 'audio.mp3'
            mimetype = a.get('mime_type', 'audio/mpeg')

        elif 'document' in message:
            d = message['document']
            file_id = d['file_id']
            filename = d.get('file_name', 'document')
            mimetype = d.get('mime_type', 'application/octet-stream')

        elif 'video' in message:
            # Video can be huge — just show placeholder
            if not text:
                text = '[🎥 Відео]'

        elif 'sticker' in message:
            if not text:
                text = f"[{message['sticker'].get('emoji', '🎭')} Стікер]"

        elif not text:
            return request.make_response('ok')

        # ── Build message body ────────────────────────────────────────────────
        if author_partner:
            body = Markup('<p>{}</p>').format(escape(text)) if text else Markup('<p></p>')
        else:
            sender_name = f"{first_name} {last_name}".strip() or username or 'TG'
            if text:
                body = Markup('<p>📱 <b>{}</b>: {}</p>').format(
                    escape(sender_name), escape(text)
                )
            else:
                body = Markup('<p>📱 <b>{}</b></p>').format(escape(sender_name))

        # ── Download and attach file ──────────────────────────────────────────
        attachment_ids = []
        if file_id and token:
            result = _tg_download(token, file_id)
            if result:
                file_bytes, dl_name, dl_mime = result
                att_name = filename or dl_name
                att_mime = mimetype or dl_mime
                att = env['ir.attachment'].sudo().create({
                    'name': att_name,
                    'type': 'binary',
                    'datas': base64.b64encode(file_bytes).decode(),
                    'res_model': 'discuss.channel',
                    'res_id': channel.id,
                    'mimetype': att_mime,
                })
                attachment_ids = [att.id]
            elif not text:
                # File too large and no text — show placeholder
                ext_name = filename or 'файл'
                body = Markup('<p>📎 <b>{}</b> (файл завеликий для завантаження)</p>').format(
                    escape(ext_name)
                )

        # ── Post to Discuss ───────────────────────────────────────────────────
        channel.sudo().with_context(tg_no_forward=True).message_post(
            body=body,
            author_id=author_partner.id if author_partner else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            attachment_ids=attachment_ids,
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

        tg_chat = request.env['rayton.telegram.chat'].sudo().search([
            ('tg_chat_id', '=', tg_chat_id),
        ], limit=1)

        if not tg_chat or not tg_chat.discuss_channel_id:
            _logger.warning("[RaytonTg] No Odoo channel linked to tg_chat_id=%s", tg_chat_id)
            return {'status': 'error', 'message': 'Chat mapping not found'}

        safe_name = escape(from_name) if from_name else 'TG'
        safe_body = escape(body)
        msg_body = Markup(f'<b>{safe_name}</b>: {safe_body}')

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

        tg_chat.promote_to_admin(tg_user_id, stored_token)
        _logger.info(
            "[RaytonTg] Promoted user %s to admin in chat %s",
            tg_user_id, tg_chat_id,
        )
        return {'status': 'ok'}

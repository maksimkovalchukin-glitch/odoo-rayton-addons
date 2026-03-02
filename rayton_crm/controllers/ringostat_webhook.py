"""
Ringostat → Odoo webhook.

Endpoint: POST /ringostat/webhook?token=TOKEN
Auth: secret token в query-параметрі ?token=

Налаштування в Odoo (одноразово через shell або Settings → Technical → Parameters):
  env['ir.config_parameter'].set_param('ringostat.webhook.token', 'СЕКРЕТНИЙ_ТОКЕН')

В n8n: додати до URL Odoo ендпоінту ?token=СЕКРЕТНИЙ_ТОКЕН
"""
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RingostatWebhookController(http.Controller):

    @http.route('/ringostat/webhook', type='http', auth='none',
                methods=['POST'], csrf=False)
    def ringostat_webhook(self, **kwargs):
        # ── Auth ──────────────────────────────────────────────────────────── #
        token = request.params.get('token', '')
        stored_token = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('ringostat.webhook.token', '')
        )
        if not stored_token or token != stored_token:
            _logger.warning(
                'Ringostat webhook: invalid token from %s',
                request.httprequest.remote_addr,
            )
            return request.make_response('Forbidden', status=403)

        # ── Parse body ────────────────────────────────────────────────────── #
        try:
            body = request.httprequest.get_data(as_text=True)
            payload = json.loads(body)
        except Exception as exc:
            _logger.error('Ringostat webhook: JSON parse error: %s', exc)
            return request.make_response('Bad Request', status=400)

        _logger.info(
            'Ringostat webhook: call_type=%s employee=%s department=%s status=%s',
            payload.get('call_type'),
            payload.get('employee'),
            payload.get('department'),
            payload.get('call_status'),
        )

        # ── Save ──────────────────────────────────────────────────────────── #
        try:
            request.env['rayton.ringostat.call'].sudo().create_from_webhook(payload)
        except Exception as exc:
            _logger.exception('Ringostat webhook: failed to save call: %s', exc)
            return request.make_response('Internal Server Error', status=500)

        return request.make_response('OK', status=200)

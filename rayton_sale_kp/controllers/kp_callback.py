import logging
from markupsafe import Markup
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class KpCallbackController(http.Controller):

    @http.route(
        '/rayton/kp/callback',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def kp_callback(self, **kwargs):
        """
        Called by n8n/Google Apps Script after PDF generation.

        Expected JSON body:
        {
            "sale_order_id": 42,
            "pdf_base64": "<base64-encoded PDF>",
            "filename": "КП_ТОВ_САНТЕКО.pdf"   (optional)
        }
        """
        sale_order_id = kwargs.get('sale_order_id')
        pdf_base64    = kwargs.get('pdf_base64')
        filename      = kwargs.get('filename') or 'КП.pdf'

        if not sale_order_id or not pdf_base64:
            _logger.warning("[rayton_sale_kp] /rayton/kp/callback: missing sale_order_id or pdf_base64")
            return {'status': 'error', 'message': 'Missing sale_order_id or pdf_base64'}

        try:
            order = request.env['sale.order'].sudo().browse(int(sale_order_id))
            if not order.exists():
                _logger.warning("[rayton_sale_kp] sale.order id=%s not found", sale_order_id)
                return {'status': 'error', 'message': f'sale.order {sale_order_id} not found'}

            # Attach the PDF
            attachment = request.env['ir.attachment'].sudo().create({
                'name':     filename,
                'type':     'binary',
                'datas':    pdf_base64,
                'res_model': 'sale.order',
                'res_id':   order.id,
                'mimetype': 'application/pdf',
            })

            # Update state and post chatter message with download link
            order.kp_state = 'done'
            pdf_link = Markup(
                f'✅ <b>Комерційна пропозиція готова!</b><br/>'
                f'📄 <a href="/web/content/{attachment.id}?download=true">'
                f'{filename}</a>'
            )
            order.sudo().message_post(
                body=pdf_link,
                attachment_ids=[attachment.id],
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

            # Mirror to linked CRM opportunity if present
            if 'opportunity_id' in order._fields and order.opportunity_id:
                lead = order.opportunity_id
                lead.message_post(
                    body=Markup(
                        f'✅ <b>Комерційна пропозиція готова!</b> '
                        f'(<a href="/odoo/sales/{order.id}">{order.name}</a>)<br/>'
                        f'📄 <a href="/web/content/{attachment.id}?download=true">'
                        f'{filename}</a>'
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )

            _logger.info(
                "[rayton_sale_kp] PDF '%s' attached to sale.order id=%s",
                filename, sale_order_id,
            )
            return {'status': 'ok', 'attachment_id': attachment.id}

        except Exception as e:
            _logger.error("[rayton_sale_kp] Callback error: %s", e, exc_info=True)
            return {'status': 'error', 'message': str(e)}

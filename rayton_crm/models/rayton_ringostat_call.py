import logging
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class RaytonRingostatCall(models.Model):
    _name = 'rayton.ringostat.call'
    _description = 'Дзвінок Ringostat'
    _order = 'call_date desc'
    _rec_name = 'employee'

    call_type = fields.Selection([
        ('transitin',  'Вхідний'),
        ('transitout', 'Вихідний'),
    ], string='Тип', required=True)
    call_date        = fields.Datetime('Дата дзвінку', required=True, index=True)
    department       = fields.Char('Відділ')
    call_status      = fields.Char('Статус', index=True)  # ANSWERED, BUSY, NO_ANSWER, FAILED
    employee         = fields.Char('Співробітник (Ringostat)')
    internal_number  = fields.Char('Внутр. номер')
    caller_number    = fields.Char('Номер того хто телефонує')
    call_destination = fields.Char('Номер виклику')
    call_duration    = fields.Integer('Тривалість, сек')
    has_recording    = fields.Boolean('Є запис')
    recording_url    = fields.Char('URL запису (ogg)')
    recording_wav    = fields.Char('URL запису (wav)')

    user_id = fields.Many2one(
        'res.users', 'Користувач Odoo', index=True,
        help='Автоматично зіставлено з employee по прізвищу',
    )
    lead_id = fields.Many2one(
        'crm.lead', 'Нагода CRM',
        help='Зіставлено по номеру телефону',
    )

    # ── helpers ──────────────────────────────────────────────────────────── #

    @api.model
    def _match_user(self, employee_name):
        """Match Ringostat employee name to res.users by last name.

        Ringostat format: "Прізвище Ім'я По-батькові"
        → extract first word as last name → ilike search in users.
        """
        if not employee_name:
            return self.env['res.users']
        last_name = employee_name.strip().split()[0]
        return self.env['res.users'].search([
            ('partner_id.name', 'ilike', last_name),
            ('active', '=', True),
            ('share', '=', False),
        ], limit=1)

    @api.model
    def _match_lead(self, phone_number):
        """Try to find an active CRM opportunity by phone number."""
        if not phone_number:
            return self.env['crm.lead']
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) < 7:
            return self.env['crm.lead']
        suffix = digits[-9:]
        phone_rec = self.env['res.partner.phone'].search(
            [('phone', 'like', suffix)], limit=1,
        )
        if not (phone_rec and phone_rec.partner_id):
            return self.env['crm.lead']
        return self.env['crm.lead'].search([
            ('partner_id', '=', phone_rec.partner_id.id),
            ('active', '=', True),
            ('type', '=', 'opportunity'),
        ], limit=1)

    # ── main entry point ─────────────────────────────────────────────────── #

    @api.model
    def create_from_webhook(self, payload):
        """Create a call record from a Ringostat webhook payload dict."""
        call_type_raw = payload.get('call_type', '')
        call_type = call_type_raw if call_type_raw in ('transitin', 'transitout') else 'transitin'

        call_date_str = payload.get('call_date', '')
        try:
            call_date = datetime.strptime(call_date_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            call_date = datetime.now()

        try:
            duration = int(payload.get('call_duration', 0))
        except (ValueError, TypeError):
            duration = 0

        has_recording = str(payload.get('has_recording', '0')) == '1'
        employee_name = payload.get('employee', '')
        user = self._match_user(employee_name)

        # For lead matching: use the external party's number
        ext_phone = (
            payload.get('caller_number', '')
            if call_type == 'transitin'
            else payload.get('call_destination', '')
        )
        lead = self._match_lead(ext_phone)

        vals = {
            'call_type':        call_type,
            'call_date':        call_date,
            'department':       payload.get('department', ''),
            'call_status':      payload.get('call_status', ''),
            'employee':         employee_name,
            'internal_number':  payload.get('internal_number', ''),
            'caller_number':    payload.get('caller_number', ''),
            'call_destination': payload.get('call_destination', ''),
            'call_duration':    duration,
            'has_recording':    has_recording,
            'recording_url':    payload.get('recording', '') or '',
            'recording_wav':    payload.get('recording_wav', '') or '',
            'user_id':          user.id if user else False,
            'lead_id':          lead.id if lead else False,
        }
        record = self.create(vals)
        _logger.info(
            'Ringostat call saved: id=%s type=%s employee=%s status=%s user=%s lead=%s',
            record.id, call_type, employee_name,
            payload.get('call_status'), user.name if user else '—',
            lead.id if lead else '—',
        )
        return record

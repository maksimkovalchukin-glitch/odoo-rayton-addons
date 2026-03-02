import logging
from datetime import datetime

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# Статуси що вважаються успішними (є розмова)
ANSWERED_STATUSES = {'ANSWERED', 'PROPER'}

# Текстові підписи статусів Ringostat
STATUS_LABELS = {
    'ANSWERED': 'Відповіли',
    'PROPER':   'Відповіли',
    'BUSY':     'Зайнято',
    'NO_ANSWER': 'Не відповіли',
    'FAILED':   'Помилка з\'єднання',
}


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
    call_status      = fields.Char('Статус', index=True)
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
        help='Перша знайдена нагода по номеру телефону',
    )

    # ── Пошук ────────────────────────────────────────────────────────────── #

    @api.model
    def _match_user(self, employee_name):
        """Match Ringostat employee name → res.users by last name."""
        if not employee_name:
            return self.env['res.users']
        last_name = employee_name.strip().split()[0]
        return self.env['res.users'].search([
            ('partner_id.name', 'ilike', last_name),
            ('active', '=', True),
            ('share', '=', False),
        ], limit=1)

    @api.model
    def _find_partners_by_phone(self, phone_number):
        """Return all res.partner records matching the given phone (last 9 digits)."""
        if not phone_number:
            return self.env['res.partner']
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) < 7:
            return self.env['res.partner']
        suffix = digits[-9:]
        phone_recs = self.env['res.partner.phone'].search([('phone', 'like', suffix)])
        return phone_recs.mapped('partner_id')

    @api.model
    def _find_leads_for_partners(self, partners):
        """Return all active open opportunities linked to these partners or their companies."""
        if not partners:
            return self.env['crm.lead']
        partner_ids = partners.ids
        # Also include parent companies
        company_ids = partners.filtered('parent_id').mapped('parent_id').ids
        all_ids = list(set(partner_ids + company_ids))
        return self.env['crm.lead'].search([
            ('partner_id', 'in', all_ids),
            ('active', '=', True),
            ('type', '=', 'opportunity'),
            ('stage_id.is_won', '=', False),
        ])

    # ── Чаттер ───────────────────────────────────────────────────────────── #

    @api.model
    def _build_call_body(self, call_type, call_status, ext_phone, duration, recording_url):
        """Build HTML body for the chatter message."""
        type_label = 'Вхідний дзвінок' if call_type == 'transitin' else 'Вихідний дзвінок'
        status_label = STATUS_LABELS.get(call_status, call_status or '—')

        dur_str = ''
        if call_status in ANSWERED_STATUSES and duration:
            m, s = duration // 60, duration % 60
            dur_str = f', {m}:{s:02d}'

        body = (
            f'<p><strong>📞 {type_label}</strong>: '
            f'{ext_phone or "—"} — {status_label}{dur_str}'
        )
        if recording_url:
            body += f'<br/><a href="{recording_url}" target="_blank">🎙 Прослухати запис</a>'
        body += '</p>'
        return body

    @api.model
    def _post_to_chatter(self, call_type, call_status, ext_phone, duration,
                         recording_url, call_date, user, partners, leads):
        """Post a call message to all relevant partner and lead chatters.

        Mirrors Pipedrive behavior: the call appears in the contact card,
        the company card, and every linked open opportunity.
        """
        body = self._build_call_body(call_type, call_status, ext_phone, duration, recording_url)

        # Activity type: Вхідний дзвінок (id=17) / Вихідний дзвінок (id=16)
        at_name = 'Вхідний дзвінок' if call_type == 'transitin' else 'Вихідний дзвінок'
        activity_type = self.env['mail.activity.type'].search(
            [('name', '=', at_name)], limit=1,
        )

        author_id = (
            user.partner_id.id if user
            else self.env.ref('base.partner_root').id
        )
        subtype_id = self.env.ref('mail.mt_note').id

        base_vals = {
            'message_type':         'comment',
            'subtype_id':           subtype_id,
            'author_id':            author_id,
            'body':                 body,
            'mail_activity_type_id': activity_type.id if activity_type else False,
            'date':                 call_date,
        }

        Msg = self.env['mail.message']

        # Post to each contact / company (deduplicated)
        posted_partner_ids = set()
        for partner in partners:
            targets = [partner]
            if partner.parent_id:
                targets.append(partner.parent_id)
            for p in targets:
                if p.id in posted_partner_ids:
                    continue
                posted_partner_ids.add(p.id)
                Msg.create(dict(base_vals, model='res.partner', res_id=p.id))

        # Post to each open opportunity (deduplicated)
        posted_lead_ids = set()
        for lead in leads:
            if lead.id in posted_lead_ids:
                continue
            posted_lead_ids.add(lead.id)
            Msg.create(dict(base_vals, model='crm.lead', res_id=lead.id))

        _logger.info(
            'Ringostat: posted call message to %d partner(s) and %d lead(s)',
            len(posted_partner_ids), len(posted_lead_ids),
        )

    # ── Основний метод ───────────────────────────────────────────────────── #

    @api.model
    def create_from_webhook(self, payload):
        """Create a call record from a Ringostat webhook payload.

        Also posts the call to chatters of matched partners and opportunities,
        mirroring Pipedrive activity display behavior.

        Returns the created record, or None if the call is between internal
        employees (external phone in rayton.ringostat.excluded.phone).
        """
        call_type_raw = payload.get('call_type', '')
        call_type = call_type_raw if call_type_raw in ('transitin', 'transitout') else 'transitin'

        # External party phone
        ext_phone = (
            payload.get('caller_number', '')
            if call_type == 'transitin'
            else payload.get('call_destination', '')
        )

        # Skip internal employee calls
        if self.env['rayton.ringostat.excluded.phone'].is_internal(ext_phone):
            _logger.info(
                'Ringostat call skipped (internal): type=%s ext_phone=%s employee=%s',
                call_type, ext_phone, payload.get('employee', ''),
            )
            return None

        # Parse date/duration
        call_date_str = payload.get('call_date', '')
        try:
            call_date = datetime.strptime(call_date_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            call_date = datetime.now()

        try:
            duration = int(payload.get('call_duration', 0))
        except (ValueError, TypeError):
            duration = 0

        call_status = payload.get('call_status', '')
        has_recording = str(payload.get('has_recording', '0')) == '1'
        recording_url = payload.get('recording', '') or ''
        employee_name = payload.get('employee', '')

        # Match user and CRM objects
        user = self._match_user(employee_name)
        partners = self._find_partners_by_phone(ext_phone)
        leads = self._find_leads_for_partners(partners)
        first_lead = leads[:1]

        # Save raw call record
        vals = {
            'call_type':        call_type,
            'call_date':        call_date,
            'department':       payload.get('department', ''),
            'call_status':      call_status,
            'employee':         employee_name,
            'internal_number':  payload.get('internal_number', ''),
            'caller_number':    payload.get('caller_number', ''),
            'call_destination': payload.get('call_destination', ''),
            'call_duration':    duration,
            'has_recording':    has_recording,
            'recording_url':    recording_url,
            'recording_wav':    payload.get('recording_wav', '') or '',
            'user_id':          user.id if user else False,
            'lead_id':          first_lead.id if first_lead else False,
        }
        record = self.create(vals)

        # Post to chatters (partner + company + leads)
        self._post_to_chatter(
            call_type, call_status, ext_phone, duration, recording_url,
            call_date, user, partners, leads,
        )

        _logger.info(
            'Ringostat call saved: id=%s type=%s employee=%s status=%s '
            'user=%s partners=%s leads=%s',
            record.id, call_type, employee_name, call_status,
            user.name if user else '—',
            partners.mapped('name'), leads.ids,
        )
        return record

import logging
from datetime import datetime

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# Статуси що вважаються успішними (є розмова)
ANSWERED_STATUSES = {'ANSWERED', 'PROPER'}

# Текстові підписи статусів Ringostat
STATUS_LABELS = {
    'ANSWERED':  'Відповіли',
    'PROPER':    'Відповіли',
    'BUSY':      'Зайнято',
    'NO_ANSWER': 'Не відповіли',
    'FAILED':    "Помилка з'єднання",
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
        'crm.lead', 'Нагода / Лід CRM',
        help='Перший знайдений або щойно створений лід',
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
    def _get_activity_type(self, call_type):
        at_name = 'Вхідний дзвінок' if call_type == 'transitin' else 'Вихідний дзвінок'
        return self.env['mail.activity.type'].search([('name', '=', at_name)], limit=1)

    @api.model
    def _make_message_vals(self, model, res_id, body, author_id,
                           activity_type, call_date, subtype_id):
        return {
            'model':                 model,
            'res_id':                res_id,
            'message_type':          'comment',
            'subtype_id':            subtype_id,
            'author_id':             author_id,
            'body':                  body,
            'mail_activity_type_id': activity_type.id if activity_type else False,
            'date':                  call_date,
        }

    @api.model
    def _post_to_chatter(self, call_type, call_status, ext_phone, duration,
                         recording_url, call_date, user, partners, leads):
        """Post a call message to all relevant partner and lead chatters.

        Mirrors Pipedrive behavior: the call appears in the contact card,
        the company card, and every linked open opportunity.
        """
        body = self._build_call_body(call_type, call_status, ext_phone, duration, recording_url)
        at = self._get_activity_type(call_type)
        author_id = (
            user.partner_id.id if user
            else self.env.ref('base.partner_root').id
        )
        subtype_id = self.env.ref('mail.mt_note').id
        Msg = self.env['mail.message']

        # Post to each contact + their company (deduplicated)
        posted_partner_ids = set()
        for partner in partners:
            targets = [partner]
            if partner.parent_id:
                targets.append(partner.parent_id)
            for p in targets:
                if p.id in posted_partner_ids:
                    continue
                posted_partner_ids.add(p.id)
                Msg.create(self._make_message_vals(
                    'res.partner', p.id, body, author_id, at, call_date, subtype_id,
                ))

        # Post to each open opportunity (deduplicated)
        posted_lead_ids = set()
        for lead in leads:
            if lead.id in posted_lead_ids:
                continue
            posted_lead_ids.add(lead.id)
            Msg.create(self._make_message_vals(
                'crm.lead', lead.id, body, author_id, at, call_date, subtype_id,
            ))

        _logger.info(
            'Ringostat: posted call to %d partner(s) and %d lead(s)',
            len(posted_partner_ids), len(posted_lead_ids),
        )

    # ── Новий лід для невідомого номера ──────────────────────────────────── #

    @api.model
    def _create_lead_for_unknown_phone(self, call_type, call_status, ext_phone,
                                       duration, recording_url, call_date, user):
        """Handle a call from/to an unknown phone: create contact + unprocessed lead.

        Creates a minimal res.partner with the phone number and a crm.lead
        (type='lead') assigned to the employee who handled the call, so the
        operator can qualify or discard it.
        """
        # Мінімальний контакт — номер телефону як ім'я (оператор уточнить пізніше)
        partner = self.env['res.partner'].sudo().create({
            'name': ext_phone or _('Невідомий контакт'),
            'company_type': 'person',
        })
        self.env['res.partner.phone'].sudo().create({
            'partner_id': partner.id,
            'phone': ext_phone,
        })

        # Команда КЦ (Оператор) — для первинної обробки
        kc_team = self.env['crm.team'].search([('name', 'ilike', 'Оператор')], limit=1)

        type_label = 'Вхідний дзвінок' if call_type == 'transitin' else 'Вихідний дзвінок'

        lead = self.env['crm.lead'].sudo().create({
            'name': f'{type_label} {ext_phone}',
            'partner_id': partner.id,
            'type': 'lead',
            'user_id': user.id if user else False,
            'team_id': kc_team.id if kc_team else False,
        })

        # Повідомлення в чаттері ліда
        body = self._build_call_body(call_type, call_status, ext_phone, duration, recording_url)
        body += '<p><em>⚠️ Невідомий номер — потребує кваліфікації</em></p>'

        at = self._get_activity_type(call_type)
        author_id = (
            user.partner_id.id if user
            else self.env.ref('base.partner_root').id
        )
        self.env['mail.message'].create(self._make_message_vals(
            'crm.lead', lead.id, body, author_id, at, call_date,
            self.env.ref('mail.mt_note').id,
        ))

        _logger.info(
            'Ringostat: created new lead id=%s for unknown phone %s, assigned to %s',
            lead.id, ext_phone, user.name if user else '—',
        )
        return lead

    # ── Основний метод ───────────────────────────────────────────────────── #

    @api.model
    def create_from_webhook(self, payload):
        """Create a call record from a Ringostat webhook payload.

        Flow:
        1. Skip internal (employee-to-employee) calls.
        2. If external phone is known → post to partner/company/lead chatters.
        3. If external phone is UNKNOWN → create new contact + unprocessed lead
           assigned to the employee who handled the call.
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

        user = self._match_user(employee_name)
        partners = self._find_partners_by_phone(ext_phone)

        if partners:
            # ── Відомий номер: публікуємо в чаттері ──
            leads = self._find_leads_for_partners(partners)
            first_lead = leads[:1]
            self._post_to_chatter(
                call_type, call_status, ext_phone, duration, recording_url,
                call_date, user, partners, leads,
            )
        else:
            # ── Невідомий номер: створюємо контакт + неопрацьований лід ──
            new_lead = self._create_lead_for_unknown_phone(
                call_type, call_status, ext_phone, duration,
                recording_url, call_date, user,
            )
            first_lead = new_lead

        # Зберігаємо сирий запис дзвінка
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
        _logger.info(
            'Ringostat call saved: id=%s type=%s employee=%s status=%s user=%s '
            'known_partner=%s lead=%s',
            record.id, call_type, employee_name, call_status,
            user.name if user else '—',
            bool(partners), first_lead.id if first_lead else '—',
        )
        return record

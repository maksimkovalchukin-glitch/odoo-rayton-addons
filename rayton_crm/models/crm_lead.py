from odoo import models, fields, api, _
from odoo.exceptions import UserError

FINANCING_TYPE = [
    ('own', 'Власні'),
    ('credit', 'Кредитні'),
    ('mixed', 'Власні (аванс)/Кредитні'),
]


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    contact_ids = fields.One2many(
        related='partner_id.child_ids',
        string='Контакти компанії',
        readonly=True,
    )
    transfer_ids = fields.One2many(
        'rayton.lead.transfer', 'lead_id',
        string='Передачі',
    )
    transfer_count = fields.Integer(
        string='Кількість передач',
        compute='_compute_transfer_count',
    )
    last_operator_id = fields.Many2one(
        'res.users', string='Оператор',
        help='Оператор що востаннє вів цей лід',
    )

    # True = лід зараз у менеджера (Sales), False = у КЦ
    is_with_manager = fields.Boolean(
        string='У менеджера',
        compute='_compute_is_with_manager',
        store=False,
    )

    # Поля проекту
    consumption = fields.Float(string='Споживання, МВт*год/міс', digits=(10, 2))
    is_bank_client = fields.Boolean(string='Банківський клієнт')
    project_type = fields.Selection([
        ('ses', 'СЕС'),
        ('uze', 'УЗЕ'),
        ('ses_uze', 'СЕС+УЗЕ'),
    ], string='Тип проекту')

    # Поля угоди (Pipedrive deals)
    power_ses_kw = fields.Float(string='Потужність СЕС, кВт', digits=(10, 2))
    capacity_uze_kwh = fields.Float(string='Ємність УЗЕ, кВт·год', digits=(10, 2))
    financing_type = fields.Selection(FINANCING_TYPE, string='Тип фінансування')
    primary_calc_date = fields.Date(string='Дата первинних розрахунків')
    measurement_date = fields.Date(string='Дата замірів')
    advance_planned_date = fields.Date(string='Планова дата авансу')
    advance_actual_date = fields.Date(string='Фактична дата авансу')
    loss_reason_text = fields.Char(string='Причина програшу')
    pipedrive_deal_id = fields.Integer(string='Pipedrive Deal ID', index=True)
    project_number = fields.Char(string='Номер проекту')
    pipedrive_next_activity_date = fields.Date(string='Наст. активність (PD)')

    # Кредитний спеціаліст угоди (заповнюється з імпорту або вручну)
    credit_specialist_id = fields.Many2one(
        'res.users', string='Кредитний спеціаліст',
    )

    def _compute_is_with_manager(self):
        kc_team = self.env['crm.team'].search([('name', 'ilike', 'Оператор')], limit=1)
        for lead in self:
            lead.is_with_manager = bool(kc_team) and lead.team_id.id != kc_team.id

    def _compute_transfer_count(self):
        for lead in self:
            lead.transfer_count = len(lead.transfer_ids)

    def action_transfer_to_manager(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Оберіть клієнта перед передачею.'))
        if not self.partner_id.parent_id and self.partner_id.company_type == 'person':
            raise UserError(_('Контакт має бути прив\'язаний до компанії.'))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Передати менеджеру',
            'res_model': 'rayton.lead.transfer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lead_id': self.id},
        }

    def action_return_to_kc(self):
        self.ensure_one()
        kc_team = self.env['crm.team'].search([('name', 'ilike', 'Оператор')], limit=1)
        kc_stage = self.env['crm.stage'].search([
            ('name', 'ilike', 'паузі'),
        ], limit=1)

        operator = self.last_operator_id or self.env['res.users'].browse(self.env.uid)

        self.write({
            'team_id': kc_team.id if kc_team else self.team_id.id,
            'stage_id': kc_stage.id if kc_stage else self.stage_id.id,
            'user_id': operator.id,
        })

        # Лог передачі
        self.env['rayton.lead.transfer'].create({
            'lead_id': self.id,
            'manager_id': self.env.uid,
            'operator_id': operator.id,
            'direction': 'to_kc',
            'state': 'active',
        })

        # Оновлюємо попередні активні записи передачі
        active_transfers = self.transfer_ids.filtered(
            lambda t: t.direction == 'to_manager' and t.state == 'active'
        )
        active_transfers.write({'state': 'returned'})

        # @mention оператора в чаттері
        self.message_post(
            body=_(
                '<p>🔄 Нагоду повернено на КЦ.<br/>'
                'Оператор: <a href="#" data-oe-model="res.users" data-oe-id="%(uid)s">%(name)s</a></p>'
            ) % {'uid': operator.id, 'name': operator.name},
            partner_ids=[operator.partner_id.id],
        )
        return True

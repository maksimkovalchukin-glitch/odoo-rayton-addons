from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class CrmLead(models.Model):
    _inherit = 'crm.lead'

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

    # Підказка кредитного спеціаліста по регіону
    credit_specialist_id = fields.Many2one(
        'res.users', string='Кредитний спеціаліст',
        compute='_compute_credit_specialist',
        store=False,
    )

    def _compute_transfer_count(self):
        for lead in self:
            lead.transfer_count = len(lead.transfer_ids)

    def _compute_credit_specialist(self):
        for lead in self:
            state = lead.partner_id.state_id if lead.partner_id else False
            lead.credit_specialist_id = state.credit_specialist_id if state else False

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
        kc_team = self.env['crm.team'].search([('name', 'ilike', 'Колл')], limit=1)
        kc_stage = self.env['crm.stage'].search([
            ('name', 'ilike', 'паузі'),
            ('team_id', '=', kc_team.id if kc_team else False),
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

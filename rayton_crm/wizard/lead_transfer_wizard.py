from odoo import models, fields, api, _
from odoo.exceptions import UserError


class RaytonLeadTransferWizard(models.TransientModel):
    _name = 'rayton.lead.transfer.wizard'
    _description = 'Wizard передачі ліда менеджеру'

    lead_id = fields.Many2one('crm.lead', required=True)
    transfer_type = fields.Selection([
        ('new', 'Новий лід'),
        ('old', 'Старий лід'),
    ], string='Тип ліда', required=True, default='new')

    suggested_manager_id = fields.Many2one(
        'res.users', string='Підказка',
        compute='_compute_suggested_manager',
    )
    manager_id = fields.Many2one(
        'res.users', string='Менеджер',
        required=True,
        domain="[('groups_id.name', 'ilike', 'Менеджер')]",
    )
    notes = fields.Text(string='Примітки')

    @api.depends('transfer_type', 'lead_id')
    def _compute_suggested_manager(self):
        for wizard in self:
            if wizard.transfer_type == 'old':
                # Попередній менеджер з логу передач
                last = wizard.lead_id.transfer_ids.filtered(
                    lambda t: t.direction == 'to_manager'
                ).sorted('create_date', reverse=True)
                wizard.suggested_manager_id = last[0].manager_id if last else False
            else:
                # Наступний в черзі
                next_q = self.env['rayton.manager.queue'].get_next_manager()
                wizard.suggested_manager_id = next_q.user_id if next_q else False

    @api.onchange('transfer_type', 'suggested_manager_id')
    def _onchange_transfer_type(self):
        self.manager_id = self.suggested_manager_id

    def action_confirm(self):
        self.ensure_one()
        lead = self.lead_id

        # Перша стадія менеджерів (is_manager_pipeline=True)
        first_stage = self.env['crm.stage'].search(
            [('is_manager_pipeline', '=', True)], order='sequence', limit=1
        )

        # Зберігаємо поточного оператора
        lead.last_operator_id = self.env.uid

        # Лід стає нагодою при передачі менеджеру
        lead.write({
            'type': 'opportunity',
            'team_id': first_stage.team_id.id if first_stage else lead.team_id.id,
            'stage_id': first_stage.id if first_stage else lead.stage_id.id,
            'user_id': self.manager_id.id,
        })

        # Лог передачі
        self.env['rayton.lead.transfer'].create({
            'lead_id': lead.id,
            'operator_id': self.env.uid,
            'manager_id': self.manager_id.id,
            'transfer_type': self.transfer_type,
            'direction': 'to_manager',
            'notes': self.notes,
            'state': 'active',
        })

        # Оновлюємо лічильник черги (тільки для нових лідів)
        if self.transfer_type == 'new':
            queue_entry = self.env['rayton.manager.queue'].search(
                [('user_id', '=', self.manager_id.id)], limit=1
            )
            if queue_entry:
                queue_entry.mark_assigned()

        # @mention менеджера в чаттері
        lead.message_post(
            body=_(
                '<p>📤 Нагоду передано менеджеру '
                '<a href="#" data-oe-model="res.users" data-oe-id="%(uid)s">%(name)s</a>'
                '%(notes)s</p>'
            ) % {
                'uid': self.manager_id.id,
                'name': self.manager_id.name,
                'notes': f'<br/>📝 {self.notes}' if self.notes else '',
            },
            partner_ids=[self.manager_id.partner_id.id],
        )
        return {'type': 'ir.actions.act_window_close'}

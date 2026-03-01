from odoo import models, fields, api, _
from odoo.exceptions import UserError


class RaytonLeadGenerateWizard(models.TransientModel):
    _name = 'rayton.lead.generate.wizard'
    _description = 'Wizard генерації лідів з компаній'

    partner_ids = fields.Many2many(
        'res.partner', string='Компанії',
        default=lambda self: self._default_partners(),
    )
    partner_count = fields.Integer(
        string='Компаній обрано',
        compute='_compute_partner_count',
    )
    assignment_mode = fields.Selection([
        ('single', 'Одному оператору'),
        ('roundrobin', 'По черзі між операторами'),
    ], string='Розподіл', default='single', required=True)
    operator_id = fields.Many2one(
        'res.users', string='Оператор',
        domain="[('groups_id.name', 'ilike', 'Оператор')]",
    )
    operator_ids = fields.Many2many(
        'res.users', 'lead_gen_wizard_operator_rel',
        string='Оператори',
        domain="[('groups_id.name', 'ilike', 'Оператор')]",
    )
    source = fields.Char(string='Джерело бази')
    skip_existing = fields.Boolean(
        string='Пропустити якщо є відкритий лід',
        default=True,
    )
    kc_team_id = fields.Many2one(
        'crm.team', string='Команда КЦ',
        default=lambda self: self.env['crm.team'].search(
            [('name', 'ilike', 'Колл')], limit=1
        ),
    )

    def _default_partners(self):
        return self.env['res.partner'].browse(self.env.context.get('active_ids', []))

    def _compute_partner_count(self):
        for wiz in self:
            wiz.partner_count = len(wiz.partner_ids)

    @api.onchange('assignment_mode')
    def _onchange_assignment_mode(self):
        self.operator_id = False
        self.operator_ids = False

    def action_generate(self):
        self.ensure_one()

        if self.assignment_mode == 'single' and not self.operator_id:
            raise UserError(_('Оберіть оператора.'))
        if self.assignment_mode == 'roundrobin' and not self.operator_ids:
            raise UserError(_('Оберіть хоча б одного оператора.'))

        operators = (
            list(self.operator_ids)
            if self.assignment_mode == 'roundrobin'
            else [self.operator_id]
        )
        op_index = 0
        created = 0
        skipped = 0

        first_stage = self.env['crm.stage'].search([
            '|',
            ('team_id', '=', self.kc_team_id.id),
            ('team_id', '=', False),
        ], order='sequence', limit=1)

        for partner in self.partner_ids.filtered(lambda p: p.is_company):
            if self.skip_existing and partner.has_open_lead:
                skipped += 1
                continue

            operator = operators[op_index % len(operators)]
            op_index += 1

            self.env['crm.lead'].create({
                'name': partner.name,
                'partner_id': partner.id,
                'type': 'lead',
                'user_id': operator.id,
                'team_id': self.kc_team_id.id,
                'stage_id': first_stage.id if first_stage else False,
                'source_id': self._get_or_create_source(),
            })
            created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Готово'),
                'message': _('Створено: %s лідів. Пропущено: %s.') % (created, skipped),
                'sticky': False,
                'type': 'success',
            },
        }

    def _get_or_create_source(self):
        if not self.source:
            return False
        source = self.env['utm.source'].search([('name', '=', self.source)], limit=1)
        if not source:
            source = self.env['utm.source'].create({'name': self.source})
        return source.id

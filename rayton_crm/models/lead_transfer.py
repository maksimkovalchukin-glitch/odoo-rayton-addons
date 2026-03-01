from odoo import models, fields


class RaytonLeadTransfer(models.Model):
    _name = 'rayton.lead.transfer'
    _description = 'Передача лідів'
    _order = 'create_date desc'
    _rec_name = 'lead_id'

    lead_id = fields.Many2one('crm.lead', string='Нагода', ondelete='set null')
    partner_id = fields.Many2one(
        'res.partner', string='Компанія',
        related='lead_id.partner_id', store=True,
    )
    operator_id = fields.Many2one('res.users', string='Оператор')
    manager_id = fields.Many2one('res.users', string='Менеджер')
    transfer_type = fields.Selection([
        ('new', 'Новий лід'),
        ('old', 'Старий лід'),
    ], string='Тип')
    direction = fields.Selection([
        ('to_manager', 'КЦ → Менеджер'),
        ('to_kc', 'Менеджер → КЦ'),
    ], string='Напрямок')
    state = fields.Selection([
        ('active', 'Активна'),
        ('returned', 'Повернено на КЦ'),
        ('won', 'Виграно'),
        ('lost', 'Програно'),
    ], string='Стан', default='active')
    notes = fields.Text(string='Примітки')
    create_date = fields.Datetime(string='Дата', readonly=True)

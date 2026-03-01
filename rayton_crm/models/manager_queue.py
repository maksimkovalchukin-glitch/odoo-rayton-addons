from odoo import models, fields, api

QUEUE_TYPES = [
    ('kcc', 'Заявки КЦ'),
    ('incoming', 'Вхідні заявки'),
    ('credit', 'Відділ кредитування'),
]


class RaytonManagerQueue(models.Model):
    _name = 'rayton.manager.queue'
    _description = 'Черга менеджерів'
    _order = 'queue_type, sequence, id'

    user_id = fields.Many2one(
        'res.users', string='Менеджер',
        required=True, ondelete='cascade',
    )
    queue_type = fields.Selection(
        QUEUE_TYPES, string='Тип черги',
        required=True, default='kcc',
    )
    sequence = fields.Integer(string='Порядок', default=10)
    is_paused = fields.Boolean(string='На паузі')
    leads_count = fields.Integer(string='Лідів отримано', default=0, readonly=True)
    last_assigned = fields.Datetime(string='Останнє призначення', readonly=True)

    _sql_constraints = [
        ('user_queue_unique', 'unique(user_id, queue_type)', 'Менеджер вже є в цій черзі'),
    ]

    @api.model
    def get_next_manager(self, queue_type='kcc'):
        active = self.search(
            [('is_paused', '=', False), ('queue_type', '=', queue_type)],
            order='sequence, last_assigned asc nulls first',
        )
        return active[0] if active else None

    def mark_assigned(self):
        self.ensure_one()
        self.write({
            'leads_count': self.leads_count + 1,
            'last_assigned': fields.Datetime.now(),
        })

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    kp_state = fields.Selection([
        ('none',    'Не сформовано'),
        ('pending', 'Формується...'),
        ('done',    'КП готова'),
    ], default='none', string='Статус КП', tracking=True)

    def action_open_kp_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Генератор КП',
            'res_model': 'kp.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_project_name': self.name or '',
                'default_manager': self.user_id.name or self.env.user.name,
            },
        }

import re
from odoo import models, fields, api


class ResPartnerPhone(models.Model):
    _name = 'res.partner.phone'
    _description = 'Телефони партнера'
    _order = 'is_primary desc, sequence, id'

    partner_id = fields.Many2one('res.partner', ondelete='cascade', required=True)
    phone = fields.Char(string='Номер', required=True)
    phone_type = fields.Selection([
        ('mobile', 'Мобільний'),
        ('org', 'Організації'),
        ('fin', 'Фінансова звітність'),
        ('work', 'Робочий'),
        ('direct', 'Прямий'),
        ('personal', 'Особистий'),
        ('other', 'Інший'),
    ], string='Тип', default='mobile', required=True)
    is_primary = fields.Boolean(string='Основний')
    sequence = fields.Integer(default=10)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('phone'):
                vals['phone'] = re.sub(r'[^\d]', '', vals['phone'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('phone'):
            vals['phone'] = re.sub(r'[^\d]', '', vals['phone'])
        return super().write(vals)

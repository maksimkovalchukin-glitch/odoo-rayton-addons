import re
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    phone_ids = fields.One2many(
        'res.partner.phone', 'partner_id',
        string='Телефони',
    )
    has_open_lead = fields.Boolean(
        string='Є відкритий лід',
        compute='_compute_has_open_lead',
        store=False,
    )

    def _compute_has_open_lead(self):
        for partner in self:
            leads = self.env['crm.lead'].search_count([
                ('partner_id', 'child_of', partner.id),
                ('active', '=', True),
            ])
            partner.has_open_lead = bool(leads)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            for f in ('phone', 'mobile'):
                if vals.get(f):
                    vals[f] = re.sub(r'[^\d]', '', vals[f])
        return super().create(vals_list)

    def write(self, vals):
        for f in ('phone', 'mobile'):
            if vals.get(f):
                vals[f] = re.sub(r'[^\d]', '', vals[f])
        return super().write(vals)

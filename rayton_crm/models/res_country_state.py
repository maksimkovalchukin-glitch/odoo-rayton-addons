from odoo import models, fields


class ResCountryState(models.Model):
    _inherit = 'res.country.state'

    credit_specialist_id = fields.Many2one(
        'res.users',
        string='Кредитний спеціаліст',
        domain="[('groups_id.name', 'ilike', 'Кредитний')]",
    )

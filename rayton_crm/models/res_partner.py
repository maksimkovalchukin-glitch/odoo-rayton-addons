import re
from odoo import models, fields, api

PARTNER_STATUS = [
    ('target', 'Цільовий'),
    ('non_target', 'Не цільовий'),
    ('undefined', 'Не визначено'),
    ('frontline', 'Прифронтовий'),
    ('no_contacts', 'Без контактів'),
    ('competitor', 'Реалізовано конкурентами'),
    ('paused', 'Територіально на паузі'),
    ('legal_rejected', 'Не пройшов перевірку юр. відділом'),
]

LEAD_TEMP = [
    ('cold', 'Cold lead'),
    ('warm', 'Warm lead'),
    ('hot', 'Hot lead'),
    ('customer', 'Customer'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    phone_ids = fields.One2many(
        'res.partner.phone', 'partner_id',
        string='Телефони',
    )
    # Поля з Pipedrive / збагачення
    edrpou = fields.Char(string='ЄДРПОУ', size=10, index=True)
    kved_name = fields.Char(string='Назва КВЕДу')
    client_status = fields.Selection(PARTNER_STATUS, string='Статус клієнта')
    lead_temp = fields.Selection(LEAD_TEMP, string='Температура ліда')
    partner_source = fields.Char(string='Джерело')
    consumption_mwh = fields.Float(string='Споживання, МВт·год/міс', digits=(10, 2))
    uze_proposal = fields.Boolean(string='Пропозиція УЗЕ')
    director_name = fields.Char(string='Керівник')
    resource_link = fields.Char(string='Посилання з ресурсу')
    pipedrive_person_id = fields.Integer(string='Pipedrive Person ID', index=True)

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

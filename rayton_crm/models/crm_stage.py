from odoo import fields, models


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    is_manager_pipeline = fields.Boolean(
        string='Воронка менеджера',
        default=False,
        help='Стадія входить у воронку менеджерів з продажу (враховується в KPI)',
    )

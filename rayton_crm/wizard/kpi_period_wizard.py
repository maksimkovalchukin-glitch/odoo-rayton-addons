from datetime import date

from odoo import fields, models


class RaytonKpiPeriodWizard(models.TransientModel):
    _name = 'rayton.kpi.period.wizard'
    _description = 'Вибір місяця для КПІ'

    period_date = fields.Date(
        string='Місяць (будь-який день)',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )

    def action_compute(self):
        self.env['rayton.manager.kpi'].action_refresh_all(self.period_date)
        return {
            'type': 'ir.actions.act_window',
            'name': 'КПІ Менеджерів',
            'res_model': 'rayton.manager.kpi',
            'view_mode': 'tree',
            'view_id': self.env.ref('rayton_crm.view_rayton_manager_kpi_tree').id,
        }

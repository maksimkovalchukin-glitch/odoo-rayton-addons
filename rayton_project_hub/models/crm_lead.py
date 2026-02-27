from odoo import models, fields


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    project_id = fields.Many2one(
        'project.project',
        string='Ініційований проект',
        readonly=True,
        copy=False,
        help='Проект, який було ініційовано з цієї нагоди',
    )
    project_initiated = fields.Boolean(
        string='Проект ініційовано',
        default=False,
        readonly=True,
        copy=False,
    )
    project_template_type = fields.Selection(
        selection=[
            ('ses', 'СЕС'),
            ('uze', 'УЗЕ'),
            ('ses_uze', 'СЕС+УЗЕ'),
        ],
        string='Тип проекту',
        readonly=True,
    )

    def action_initiate_project(self):
        """Open wizard to choose project template type."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ініціювати проект',
            'res_model': 'rayton.project.initiate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_id': self.id,
                'default_lead_name': self.name,
            },
        }

    def action_open_project(self):
        """Open the initiated project."""
        self.ensure_one()
        if not self.project_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

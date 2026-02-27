import logging
from markupsafe import Markup
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Map template type → project.project template name (must exist in DB)
TEMPLATE_NAMES = {
    'ses': 'СЕС',
    'uze': 'УЗЕ',
    'ses_uze': 'СЕС+УЗЕ',
}


class RaytonProjectInitiateWizard(models.TransientModel):
    _name = 'rayton.project.initiate.wizard'
    _description = 'Wizard: Ініціювати проект з нагоди'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Нагода',
        required=True,
        readonly=True,
    )
    lead_name = fields.Char(
        string='Назва угоди',
        readonly=True,
    )
    template_type = fields.Selection(
        selection=[
            ('ses', 'СЕС'),
            ('uze', 'УЗЕ'),
            ('ses_uze', 'СЕС+УЗЕ'),
        ],
        string='Тип проекту',
        required=True,
    )
    project_name = fields.Char(
        string='Назва проекту',
        compute='_compute_project_name',
        store=False,
        readonly=True,
    )

    @api.depends('lead_name', 'template_type')
    def _compute_project_name(self):
        for rec in self:
            if rec.lead_name and rec.template_type:
                label = TEMPLATE_NAMES.get(rec.template_type, '')
                rec.project_name = f"{rec.lead_name} [{label}]"
            else:
                rec.project_name = rec.lead_name or ''

    def action_confirm(self):
        """
        Main action:
        1. Find project template by type
        2. Create project from template with lead name
        3. Create Discuss channel with same name
        4. Link channel to project
        5. Link project to lead
        6. Send webhook to n8n
        """
        self.ensure_one()

        if not self.lead_id:
            raise UserError(_('Не знайдено нагоду.'))

        if self.lead_id.project_initiated:
            raise UserError(_(
                'Проект для цієї нагоди вже було ініційовано: %s'
            ) % self.lead_id.project_id.name)

        template_label = TEMPLATE_NAMES.get(self.template_type, self.template_type)
        project_name = f"{self.lead_id.name} [{template_label}]"

        # ── 1. Find template project ────────────────────────────────────────
        template = self.env['project.project'].search([
            ('name', '=', template_label),
            ('active', 'in', [True, False]),
        ], limit=1)

        # ── 2. Create project ────────────────────────────────────────────────
        if template:
            # Copy from template
            new_project = template.copy(default={
                'name': project_name,
                'active': True,
                'user_id': self.env.user.id,
                'crm_lead_id': self.lead_id.id,
                'project_template_type': self.template_type,
            })
        else:
            # No template found - create blank project
            _logger.warning(
                "[RaytonProjectHub] Template '%s' not found, creating blank project.",
                template_label
            )
            new_project = self.env['project.project'].create({
                'name': project_name,
                'user_id': self.env.user.id,
                'crm_lead_id': self.lead_id.id,
                'project_template_type': self.template_type,
            })

        # ── 3. Create Discuss channel ────────────────────────────────────────
        channel = self.env['discuss.channel'].create({
            'name': project_name,
            'channel_type': 'channel',
            'description': f'Канал проекту: {project_name}. Нагода: {self.lead_id.name}',
        })

        # Add current user as channel member
        channel.add_members(partner_ids=[self.env.user.partner_id.id])

        # ── 4. Link channel to project ────────────────────────────────────────
        new_project.discuss_channel_id = channel.id

        # Post project info as the first message in the Discuss channel
        # so that team members always have a link back to the project.
        channel.message_post(
            body=Markup(
                f'🗂 <b>Проект:</b> <a href="/web#model=project.project'
                f'&id={new_project.id}&view_type=form">{project_name}</a><br/>'
                f'📋 Тип: <b>{template_label}</b><br/>'
                f'💼 Нагода: <b>{self.lead_id.name}</b>'
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # ── 5. Link project & mark lead as initiated ──────────────────────────
        self.lead_id.write({
            'project_id': new_project.id,
            'project_initiated': True,
            'project_template_type': self.template_type,
        })

        # Post message on lead chatter
        self.lead_id.message_post(
            body=Markup(
                f'🚀 <b>Проект ініційовано</b><br/>'
                f'Тип: <b>{template_label}</b><br/>'
                f'Проект: <a href="/web#model=project.project&id={new_project.id}&view_type=form">{project_name}</a><br/>'
                f'Канал Discuss: <b>#{channel.name}</b>'
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # ── 6. Send webhook ────────────────────────────────────────────────────
        new_project._send_webhook(channel, self.env.user)

        # ── 7. Return action to open the new project task list in list view ───
        return {
            'type': 'ir.actions.act_window',
            'name': project_name,
            'res_model': 'project.task',
            'view_mode': 'list,kanban,form',
            'domain': [('project_id', '=', new_project.id)],
            'context': {
                'default_project_id': new_project.id,
                'active_id': new_project.id,
            },
            'target': 'current',
        }

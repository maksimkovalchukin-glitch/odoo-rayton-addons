import requests
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

WEBHOOK_URL = "https://n8n.rayton.net/webhook/ca5cf6c3-a92e-470a-8af1-38b14b0ffff7"


class ProjectProject(models.Model):
    _inherit = 'project.project'

    discuss_channel_id = fields.Many2one(
        'discuss.channel',
        string='Канал обговорення',
        help='Прив\'язаний канал Discuss для цього проекту.',
        domain=[('channel_type', '=', 'channel')],
        ondelete='set null',
    )
    discuss_channel_name = fields.Char(
        related='discuss_channel_id.name',
        string='Назва каналу',
        readonly=True,
    )
    crm_lead_id = fields.Many2one(
        'crm.lead',
        string='CRM Нагода',
        readonly=True,
        help='Нагода, з якої було ініційовано цей проект',
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

    def action_create_discuss_channel(self):
        """Create and link a Discuss channel for this project if not already linked."""
        self.ensure_one()
        if self.discuss_channel_id:
            return {
                'channel_id': self.discuss_channel_id.id,
                'channel_name': self.discuss_channel_id.name,
            }
        channel = self.env['discuss.channel'].create({
            'name': self.name,
            'channel_type': 'channel',
            'description': f'Канал проекту: {self.name}',
        })
        channel.add_members(partner_ids=[self.env.user.partner_id.id])
        self.discuss_channel_id = channel.id
        return {
            'channel_id': channel.id,
            'channel_name': channel.name,
        }

    def _send_webhook(self, channel, initiator_user):
        """Send project initiation data to n8n webhook."""
        payload = {
            'event': 'project_initiated',
            'project': {
                'id': self.id,
                'name': self.name,
                'template_type': self.project_template_type,
            },
            'channel': {
                'id': channel.id,
                'name': channel.name,
                'uuid': channel.uuid,
            },
            'initiator': {
                'id': initiator_user.id,
                'name': initiator_user.name,
                'login': initiator_user.login,
                'email': initiator_user.email,
            },
            'crm_lead': {
                'id': self.crm_lead_id.id if self.crm_lead_id else None,
                'name': self.crm_lead_id.name if self.crm_lead_id else None,
            },
        }
        try:
            resp = requests.post(
                WEBHOOK_URL,
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'},
            )
            _logger.info(
                "[RaytonProjectHub] Webhook sent. Status: %s, Response: %s",
                resp.status_code, resp.text[:200],
            )
        except Exception as e:
            _logger.warning("[RaytonProjectHub] Webhook failed: %s", str(e))

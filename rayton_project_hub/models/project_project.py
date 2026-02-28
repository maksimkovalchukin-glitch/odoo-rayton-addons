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

    def action_get_channel_info(self):
        """Return channel info for this project, ensuring current user is a member."""
        self.ensure_one()
        if not self.discuss_channel_id:
            return {'channel_id': False, 'channel_name': ''}
        channel = self.discuss_channel_id
        partner = self.env.user.partner_id
        # Auto-join the user so they can read and send messages
        is_member = channel.channel_member_ids.filtered(
            lambda m: m.partner_id.id == partner.id
        )
        if not is_member:
            channel.add_members(partner_ids=[partner.id])
        return {
            'channel_id': channel.id,
            'channel_name': channel.name,
        }

    def action_create_discuss_channel(self):
        """Create and link a Discuss channel for this project if not already linked."""
        self.ensure_one()
        if self.discuss_channel_id:
            # Ensure current user is a member
            channel = self.discuss_channel_id
            partner = self.env.user.partner_id
            if not channel.channel_member_ids.filtered(lambda m: m.partner_id.id == partner.id):
                channel.add_members(partner_ids=[partner.id])
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

    def _send_webhook(self, channel, initiator_user, tg_chat=None):
        """Send project initiation data to n8n webhook."""
        # Resolve TG chat if not passed directly
        if tg_chat is None:
            tg_chat = self.env['rayton.telegram.chat'].search([
                ('discuss_channel_id', '=', channel.id),
            ], limit=1)

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
            'tg_chat_id': tg_chat.tg_chat_id if tg_chat else None,
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

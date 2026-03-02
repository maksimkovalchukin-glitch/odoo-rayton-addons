import logging

import requests
from markupsafe import Markup, escape
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
    lead_x_coordinates = fields.Char(
        string='Координати / Google Maps',
        related='lead_id.x_coordinates',
        readonly=False,
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
    client_notes = fields.Text(
        string='Побажання клієнта',
        help='Менеджер коротко підсумовує побажання та особливості клієнта',
    )
    lead_info_summary = fields.Html(
        string='Інформація про проект',
        compute='_compute_lead_info_summary',
        store=False,
    )

    @api.depends('lead_name', 'template_type')
    def _compute_project_name(self):
        for rec in self:
            if rec.lead_name and rec.template_type:
                label = TEMPLATE_NAMES.get(rec.template_type, '')
                rec.project_name = f"{rec.lead_name} [{label}]"
            else:
                rec.project_name = rec.lead_name or ''

    @api.depends('lead_id', 'lead_id.x_coordinates')
    def _compute_lead_info_summary(self):
        for rec in self:
            lead = rec.lead_id
            if not lead:
                rec.lead_info_summary = ''
                continue

            rows = []

            solar_power = getattr(lead, 'x_solar_power', 0) or 0
            storage_kwh = getattr(lead, 'x_storage_capacity_kwh', 0) or 0
            system_type = getattr(lead, 'x_enegy_system_type', '') or ''
            project_cat = getattr(lead, 'x_progectn', '') or ''

            if solar_power:
                rows.append(f'☀️ <b>Потужність СЕС:</b> {solar_power} кВт')
            if storage_kwh:
                rows.append(f'🔋 <b>Ємність УЗЕ:</b> {storage_kwh} кВт·год')
            if system_type:
                rows.append(f'⚡ <b>Тип системи:</b> {system_type}')
            if project_cat:
                rows.append(f'🏗 <b>Категорія:</b> {project_cat}')

            partner = lead.partner_id
            if partner:
                addr_parts = [p for p in [
                    partner.street, partner.city, partner.country_id.name
                ] if p]
                if addr_parts:
                    rows.append(f'📍 <b>Адреса:</b> {", ".join(addr_parts)}')

            contact_name = lead.contact_name or (partner.name if partner else '')
            phone = lead.phone or lead.mobile or ''
            if contact_name:
                contact_str = contact_name
                if phone:
                    contact_str += f', {phone}'
                rows.append(f'👤 <b>Контакт:</b> {contact_str}')

            coords = lead.x_coordinates or ''
            if coords:
                if coords.startswith('http'):
                    rows.append(
                        f'🗺 <b>Координати:</b> <a href="{coords}" target="_blank">Google Maps</a>'
                    )
                else:
                    rows.append(f'🗺 <b>Координати:</b> {coords}')

            if rows:
                rec.lead_info_summary = Markup('<br/>').join(Markup(r) for r in rows)
            else:
                rec.lead_info_summary = Markup('<em style="color:#888;">Немає додаткових даних про об\'єкт</em>')

    def _build_rich_body(self, project_name, template_label, new_project, channel):
        """Build rich HTML initiation message for channel and chatter."""
        lead = self.lead_id
        parts = [
            f'🗂 <b>Проект:</b> <a href="/web#model=project.project'
            f'&id={new_project.id}&view_type=form">{project_name}</a>',
            f'📋 <b>Тип:</b> {template_label}',
            f'💼 <b>Нагода:</b> {lead.name}',
        ]

        solar_power = getattr(lead, 'x_solar_power', 0) or 0
        storage_kwh = getattr(lead, 'x_storage_capacity_kwh', 0) or 0
        system_type = getattr(lead, 'x_enegy_system_type', '') or ''
        project_cat = getattr(lead, 'x_progectn', '') or ''

        if solar_power:
            parts.append(f'☀️ <b>Потужність СЕС:</b> {solar_power} кВт')
        if storage_kwh:
            parts.append(f'🔋 <b>Ємність УЗЕ:</b> {storage_kwh} кВт·год')
        if system_type:
            parts.append(f'⚡ <b>Тип системи:</b> {system_type}')
        if project_cat:
            parts.append(f'🏗 <b>Категорія:</b> {project_cat}')

        partner = lead.partner_id
        if partner:
            addr_parts = [p for p in [
                partner.street, partner.city, partner.country_id.name
            ] if p]
            if addr_parts:
                parts.append(f'📍 <b>Адреса:</b> {", ".join(addr_parts)}')

        contact_name = lead.contact_name or (partner.name if partner else '')
        phone = lead.phone or lead.mobile or ''
        if contact_name:
            contact_str = contact_name
            if phone:
                contact_str += f', {phone}'
            parts.append(f'👤 <b>Контакт:</b> {contact_str}')

        coords = lead.x_coordinates or ''
        if coords:
            if coords.startswith('http'):
                parts.append(
                    f'🗺 <b>Координати:</b> <a href="{coords}" target="_blank">Google Maps</a>'
                )
            else:
                parts.append(f'🗺 <b>Координати:</b> {coords}')

        parts.append(f'💬 <b>Канал Discuss:</b> #{channel.name}')

        if self.client_notes:
            safe_notes = str(escape(self.client_notes)).replace('\n', '<br/>')
            parts.append(f'📝 <b>Побажання клієнта:</b><br/>{safe_notes}')

        return Markup('<br/>').join(Markup(p) for p in parts)

    def _build_tg_summary(self, project_name, template_label):
        """Build a Telegram-compatible HTML summary for pinning in the TG group."""
        lead = self.lead_id
        lines = [f'🚀 <b>Проект ініційовано!</b>\n━━━━━━━━━━━━━━━━━━━━━━']
        lines.append(f'🗂 <b>Проект:</b> {project_name}')
        lines.append(f'📋 <b>Тип:</b> {template_label}')

        solar_power = getattr(lead, 'x_solar_power', 0) or 0
        storage_kwh = getattr(lead, 'x_storage_capacity_kwh', 0) or 0
        system_type = getattr(lead, 'x_enegy_system_type', '') or ''
        project_cat = getattr(lead, 'x_progectn', '') or ''

        if solar_power:
            lines.append(f'☀️ <b>Потужність СЕС:</b> {solar_power} кВт')
        if storage_kwh:
            lines.append(f'🔋 <b>Ємність УЗЕ:</b> {storage_kwh} кВт·год')
        if system_type:
            lines.append(f'⚡ <b>Тип системи:</b> {system_type}')
        if project_cat:
            lines.append(f'🏗 <b>Категорія:</b> {project_cat}')

        partner = lead.partner_id
        if partner:
            addr_parts = [p for p in [
                partner.street, partner.city, partner.country_id.name
            ] if p]
            if addr_parts:
                lines.append(f'📍 <b>Адреса:</b> {", ".join(addr_parts)}')

        contact_name = lead.contact_name or (partner.name if partner else '')
        phone = lead.phone or lead.mobile or ''
        if contact_name:
            contact_str = contact_name
            if phone:
                contact_str += f', {phone}'
            lines.append(f'👤 <b>Контакт:</b> {contact_str}')

        coords = lead.x_coordinates or ''
        if coords:
            if coords.startswith('http'):
                lines.append(f'🗺 <b>Координати:</b> <a href="{coords}">Google Maps</a>')
            else:
                lines.append(f'🗺 <b>Координати:</b> {coords}')

        if self.client_notes:
            lines.append(f'📝 <b>Побажання клієнта:</b>\n{self.client_notes}')

        return '\n'.join(lines)

    def action_confirm(self):
        """
        Main action:
        1. Validate coordinates are filled
        2. Find project template by type
        3. Create project from template with lead name
        4. Create Discuss channel with same name
        5. Link channel to project
        6. Link project to lead
        7. Post rich info message to channel + lead chatter
        8. Send webhook to n8n
        """
        self.ensure_one()

        if not self.lead_id:
            raise UserError(_('Не знайдено нагоду.'))

        if self.lead_id.project_initiated:
            raise UserError(_(
                'Проект для цієї нагоди вже було ініційовано: %s'
            ) % self.lead_id.project_id.name)

        # ── Validate coordinates ─────────────────────────────────────────────
        if not self.lead_x_coordinates:
            raise UserError(_(
                'Координати об\'єкту обов\'язкові для ініціації проекту.\n'
                'Введіть посилання Google Maps або GPS-координати у полі "Координати".'
            ))

        template_label = TEMPLATE_NAMES.get(self.template_type, self.template_type)
        project_name = f"{self.lead_id.name} [{template_label}]"

        # ── 1. Find template project ────────────────────────────────────────
        template = self.env['project.project'].search([
            ('name', '=', template_label),
            ('active', 'in', [True, False]),
        ], limit=1)

        # ── 2. Create project ────────────────────────────────────────────────
        if template:
            new_project = template.copy(default={
                'name': project_name,
                'active': True,
                'user_id': self.env.user.id,
                'crm_lead_id': self.lead_id.id,
                'project_template_type': self.template_type,
            })
        else:
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

        # ── 4b. Create Telegram group via Telethon ────────────────────────────
        tg_chat = self._create_tg_group_via_telethon(project_name, new_project, channel)

        token = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_bot_token', ''
        )
        if token and tg_chat:
            tg_chat.post_and_pin(
                self._build_tg_summary(project_name, template_label),
                token,
            )

        # ── 5. Build rich initiation body ─────────────────────────────────────
        rich_body = self._build_rich_body(project_name, template_label, new_project, channel)

        # Post rich info as first message in channel.
        # tg_no_forward=True because post_and_pin() already sent the summary to TG.
        channel.with_context(tg_no_forward=True).message_post(
            body=rich_body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # ── 6. Link project & mark lead as initiated ──────────────────────────
        self.lead_id.write({
            'project_id': new_project.id,
            'project_initiated': True,
            'project_template_type': self.template_type,
        })

        # Post rich message on lead chatter
        lead_body = Markup('🚀 <b>Проект ініційовано</b><br/>') + rich_body
        self.lead_id.message_post(
            body=lead_body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # ── 7. Send webhook ────────────────────────────────────────────────────
        new_project._send_webhook(channel, self.env.user, tg_chat=tg_chat)

        # ── 8. Return action to open the new project task list ─────────────────
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

    def _create_tg_group_via_telethon(self, project_name, new_project, channel):
        """
        Create a Telegram supergroup via the Telethon microservice and save to pool.
        Adds the initiator (telegram_username from res.users) and all mandatory members.
        Returns rayton.telegram.chat record or None on failure.
        """
        service_url = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_service_url', ''
        )
        service_secret = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_service_secret', ''
        )
        if not service_url or not service_secret:
            _logger.warning(
                "[RaytonProjectHub] Telethon service not configured — TG group not created."
            )
            return None

        def _norm(u):
            u = (u or '').strip()
            return u if u.startswith('@') else f'@{u}' if u else None

        usernames = []
        admin_usernames = []

        # Initiator — always added as admin
        initiator_username = _norm(getattr(self.env.user, 'telegram_username', '') or '')
        if initiator_username:
            usernames.append(initiator_username)
            admin_usernames.append(initiator_username)

        # Mandatory members configured in Налаштування → Учасники Telegram груп
        mandatory = self.env['rayton.telegram.member'].search([('role', '=', 'mandatory')])
        for m in mandatory:
            uname = _norm(m.username)
            if uname and uname not in usernames:
                usernames.append(uname)
                if m.is_admin:
                    admin_usernames.append(uname)

        try:
            resp = requests.post(
                f'{service_url.rstrip("/")}/create_group',
                json={
                    'title': project_name,
                    'usernames': usernames,
                    'admin_usernames': admin_usernames,
                },
                headers={'x-secret': service_secret},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            _logger.warning("[RaytonProjectHub] TG group creation failed: %s", e)
            return None

        if data.get('status') != 'ok':
            _logger.warning("[RaytonProjectHub] TG service error: %s", data)
            return None

        tg_chat = self.env['rayton.telegram.chat'].create({
            'name': project_name,
            'tg_chat_id': data['chat_id'],
            'state': 'busy',
            'project_id': new_project.id,
            'discuss_channel_id': channel.id,
        })
        _logger.info(
            "[RaytonProjectHub] TG group created: %s (%s)", project_name, data['chat_id']
        )
        return tg_chat

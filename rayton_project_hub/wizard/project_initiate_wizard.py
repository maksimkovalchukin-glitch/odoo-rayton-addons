import logging
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

        # ── 4b. Auto-assign a free Telegram chat ──────────────────────────────
        tg_chat = self.env['rayton.telegram.chat'].search([
            ('state', '=', 'free'),
        ], limit=1)
        if not tg_chat:
            raise UserError(_(
                'Неможливо ініціювати проект: у пулі не залишилося вільних Telegram-груп.\n\n'
                'Будь ласка, зверніться до адміністратора — потрібно додати нові групи у розділі\n'
                'Проект → Конфігурація → Telegram групи.'
            ))

        tg_chat.write({
            'state': 'busy',
            'project_id': new_project.id,
            'discuss_channel_id': channel.id,
        })
        _logger.info(
            "[RaytonProjectHub] TG chat assigned: %s (%s)",
            tg_chat.name, tg_chat.tg_chat_id,
        )

        # Rename TG group, try to promote initiator to admin, send DM with invite link
        token = self.env['ir.config_parameter'].sudo().get_param(
            'rayton_project_hub.tg_bot_token', ''
        )
        invite_link = None
        tg_user_id = getattr(self.env.user, 'tg_user_id', '') or ''

        if token:
            tg_chat.rename_chat(project_name, token)

            # Try to promote immediately — works if initiator is already in the group
            if tg_user_id:
                tg_chat.promote_to_admin(tg_user_id, token)

            # Create personal invite link (one-time, 7 days)
            invite_link = tg_chat.create_invite_link(token)

            # Send invite link as Telegram DM to initiator (requires /start to bot first)
            if tg_user_id and invite_link:
                tg_chat.send_dm(tg_user_id, (
                    f'🚀 <b>Проект ініційовано:</b> {project_name}\n\n'
                    f'Ваше персональне запрошення до TG групи:\n{invite_link}\n\n'
                    f'Після вступу натисніть кнопку нижче щоб стати адміністратором.'
                ), token)
        else:
            _logger.warning("[RaytonProjectHub] TG bot token not set — cannot configure TG group.")

        # ── 5. Build rich initiation body ─────────────────────────────────────
        rich_body = self._build_rich_body(project_name, template_label, new_project, channel)

        # Post rich info as first message in channel
        channel.message_post(
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

        # Post rich message on lead chatter (+ personal TG invite link if generated)
        lead_body = Markup('🚀 <b>Проект ініційовано</b><br/>') + rich_body
        if invite_link:
            lead_body += Markup(
                f'<br/>🔗 <b>Запрошення до Telegram групи</b> (для ініціатора, діє 7 днів):<br/>'
                f'<a href="{invite_link}">{invite_link}</a>'
            )
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

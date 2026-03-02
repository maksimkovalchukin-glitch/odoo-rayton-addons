from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class RaytonManagerKpi(models.Model):
    _name = 'rayton.manager.kpi'
    _description = 'КПІ Менеджера з продажу'
    _rec_name = 'user_id'
    _order = 'lead_count desc'

    user_id = fields.Many2one('res.users', string='Менеджер', required=True, ondelete='cascade')
    period_label = fields.Char('Місяць', readonly=True)
    computed_at = fields.Datetime('Оновлено', readonly=True)

    # ── KPI 1: воронка ──────────────────────────────────────────────────── #
    lead_count = fields.Integer('Клієнтів у воронці', readonly=True)

    # ── KPI 2: якість ведення CRM ──────────────────────────────────────── #
    leads_with_comm    = fields.Integer('Лідів з дзвінком/зустріччю (міс)', readonly=True)
    leads_with_planned = fields.Integer('Лідів із запланованою комунікацією', readonly=True)
    overdue_count      = fields.Integer('Прострочені завдання', readonly=True)

    # ── KPI 3: заповнення картки ────────────────────────────────────────── #
    leads_with_lpr         = fields.Integer('Лідів з ЛПР/ЛВР', readonly=True)
    leads_with_project_num = fields.Integer('Лідів з № проекту', readonly=True)
    leads_with_advance     = fields.Integer('Лідів з датою авансу', readonly=True)
    leads_with_product     = fields.Integer('Лідів з продуктом', readonly=True)
    leads_with_power       = fields.Integer('Лідів з потужністю', readonly=True)

    # ── KPI 4: зустрічі ─────────────────────────────────────────────────── #
    meeting_count = fields.Integer('Зустрічей за місяць', readonly=True)

    # ── Обчислені відсотки ──────────────────────────────────────────────── #
    comm_pct        = fields.Float('% комунікація (міс)',   digits=(5, 1), compute='_compute_pct')
    planned_pct     = fields.Float('% заплановано',         digits=(5, 1), compute='_compute_pct')
    lpr_pct         = fields.Float('% ЛПР/ЛВР',            digits=(5, 1), compute='_compute_pct')
    project_num_pct = fields.Float('% № проекту',           digits=(5, 1), compute='_compute_pct')
    advance_pct     = fields.Float('% дата авансу',         digits=(5, 1), compute='_compute_pct')
    product_pct     = fields.Float('% продукт',             digits=(5, 1), compute='_compute_pct')
    power_pct       = fields.Float('% потужність',          digits=(5, 1), compute='_compute_pct')
    meeting_pct     = fields.Float('% план зустрічей (20)', digits=(5, 1), compute='_compute_pct')

    @api.depends(
        'lead_count', 'leads_with_comm', 'leads_with_planned',
        'leads_with_lpr', 'leads_with_project_num', 'leads_with_advance',
        'leads_with_product', 'leads_with_power', 'meeting_count',
    )
    def _compute_pct(self):
        for r in self:
            b = r.lead_count or 1
            r.comm_pct        = round(100.0 * r.leads_with_comm / b, 1)
            r.planned_pct     = round(100.0 * r.leads_with_planned / b, 1)
            r.lpr_pct         = round(100.0 * r.leads_with_lpr / b, 1)
            r.project_num_pct = round(100.0 * r.leads_with_project_num / b, 1)
            r.advance_pct     = round(100.0 * r.leads_with_advance / b, 1)
            r.product_pct     = round(100.0 * r.leads_with_product / b, 1)
            r.power_pct       = round(100.0 * r.leads_with_power / b, 1)
            r.meeting_pct     = round(100.0 * r.meeting_count / 20, 1)

    # ── Розрахунок ──────────────────────────────────────────────────────── #

    def action_refresh_all(self):
        today = date.today()
        first_day      = today.replace(day=1)
        last_day       = first_day + relativedelta(months=1) - relativedelta(days=1)
        next_mo_start  = first_day + relativedelta(months=1)
        next_mo_end    = next_mo_start + relativedelta(months=1) - relativedelta(days=1)
        period_label   = first_day.strftime('%m.%Y')

        # Типи активностей: дзвінки + зустрічі (без Недозвону)
        comm_types = self.env['mail.activity.type'].search([('name', 'in', [
            'Телефонний дзвінок Клієнту', 'Вихідний дзвінок', 'Вхідний дзвінок',
            'Онлайн-зустріч', 'Офлайн-зустріч',
        ])])
        meeting_types = self.env['mail.activity.type'].search([('name', 'in', [
            'Онлайн-зустріч', 'Офлайн-зустріч',
        ])])
        comm_type_ids   = comm_types.ids or [0]
        meeting_type_ids = meeting_types.ids or [0]

        manager_group  = self.env.ref('rayton_crm.group_manager')
        kc_head_group  = self.env.ref('rayton_crm.group_kc_head')
        managers = (manager_group.users - kc_head_group.users).filtered(
            lambda u: u.active and not u.share and u.id != 1
        )

        # Видалити записи для юзерів яких більше немає в списку менеджерів
        self.search([('user_id', 'not in', managers.ids)]).unlink()

        for manager in managers:
            leads = self.env['crm.lead'].search([
                ('user_id', '=', manager.id),
                ('active', '=', True),
                ('stage_id.is_won', '=', False),
                ('type', '=', 'opportunity'),
            ])
            lead_ids = leads.ids
            if not lead_ids:
                continue

            cr = self.env.cr

            # 2a: дзвінки/зустрічі цього місяця
            cr.execute("""
                SELECT COUNT(DISTINCT res_id)
                FROM mail_message
                WHERE model = 'crm.lead'
                  AND res_id = ANY(%s)
                  AND mail_activity_type_id = ANY(%s)
                  AND date >= %s AND date <= %s
            """, [lead_ids, comm_type_ids, first_day, last_day])
            leads_with_comm = cr.fetchone()[0]

            # 2b: заплановані на наступний місяць
            cr.execute("""
                SELECT COUNT(DISTINCT res_id)
                FROM mail_activity
                WHERE res_model = 'crm.lead'
                  AND res_id = ANY(%s)
                  AND date_deadline >= %s AND date_deadline <= %s
            """, [lead_ids, next_mo_start, next_mo_end])
            leads_with_planned = cr.fetchone()[0]

            # 2c: прострочені завдання
            cr.execute("""
                SELECT COUNT(*)
                FROM mail_activity
                WHERE res_model = 'crm.lead'
                  AND res_id = ANY(%s)
                  AND date_deadline < %s
            """, [lead_ids, today])
            overdue_count = cr.fetchone()[0]

            # 3a: ЛПР/ЛВР — партнер має дочірній контакт з заповненою посадою
            cr.execute("""
                SELECT COUNT(DISTINCT l.id)
                FROM crm_lead l
                JOIN res_partner c ON c.parent_id = l.partner_id
                WHERE l.id = ANY(%s)
                  AND c.function IS NOT NULL AND c.function != ''
            """, [lead_ids])
            leads_with_lpr = cr.fetchone()[0]

            # 3b–3e: заповнення картки (один запит)
            cr.execute("""
                SELECT
                    COUNT(CASE WHEN project_number IS NOT NULL AND project_number != '' THEN 1 END),
                    COUNT(CASE WHEN advance_planned_date IS NOT NULL THEN 1 END),
                    COUNT(CASE WHEN project_type IS NOT NULL THEN 1 END),
                    COUNT(CASE WHEN power_ses_kw > 0 OR capacity_uze_kwh > 0 THEN 1 END)
                FROM crm_lead
                WHERE id = ANY(%s)
            """, [lead_ids])
            row = cr.fetchone()
            leads_with_project_num = row[0]
            leads_with_advance     = row[1]
            leads_with_product     = row[2]
            leads_with_power       = row[3]

            # 4: зустрічі цього місяця
            cr.execute("""
                SELECT COUNT(*)
                FROM mail_message
                WHERE model = 'crm.lead'
                  AND res_id = ANY(%s)
                  AND mail_activity_type_id = ANY(%s)
                  AND date >= %s AND date <= %s
            """, [lead_ids, meeting_type_ids, first_day, last_day])
            meeting_count = cr.fetchone()[0]

            vals = {
                'lead_count':             len(lead_ids),
                'leads_with_comm':        leads_with_comm,
                'leads_with_planned':     leads_with_planned,
                'overdue_count':          overdue_count,
                'leads_with_lpr':         leads_with_lpr,
                'leads_with_project_num': leads_with_project_num,
                'leads_with_advance':     leads_with_advance,
                'leads_with_product':     leads_with_product,
                'leads_with_power':       leads_with_power,
                'meeting_count':          meeting_count,
                'period_label':           period_label,
                'computed_at':            fields.Datetime.now(),
            }

            existing = self.search([('user_id', '=', manager.id)], limit=1)
            if existing:
                existing.write(vals)
            else:
                vals['user_id'] = manager.id
                self.create(vals)

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open_kpi(self):
        self.action_refresh_all()
        return {
            'type': 'ir.actions.act_window',
            'name': 'КПІ Менеджерів',
            'res_model': 'rayton.manager.kpi',
            'view_mode': 'tree',
            'view_id': self.env.ref('rayton_crm.view_rayton_manager_kpi_tree').id,
        }

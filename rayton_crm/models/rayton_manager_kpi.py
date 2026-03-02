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

    # ── Розбивка дзвінків: телефонія vs ручні ───────────────────────────── #
    comm_total  = fields.Integer('Дзвінків всього (міс)',    readonly=True)
    comm_auto   = fields.Integer('Дзвінків телефонія (міс)', readonly=True)
    comm_manual = fields.Integer('Дзвінків ручних (міс)',    readonly=True)

    # ── KPI 3: заповнення картки ────────────────────────────────────────── #
    leads_with_lpr         = fields.Integer('Лідів з ЛПР/ЛВР', readonly=True)
    leads_with_project_num = fields.Integer('Лідів з № проекту', readonly=True)
    leads_with_advance     = fields.Integer('Лідів з датою авансу', readonly=True)
    leads_with_product     = fields.Integer('Лідів з продуктом', readonly=True)
    leads_with_power       = fields.Integer('Лідів з потужністю', readonly=True)

    # ── KPI 4: зустрічі ─────────────────────────────────────────────────── #
    meeting_count = fields.Integer('Зустрічей за місяць', readonly=True)

    # ── Ringostat дзвінки за місяць ─────────────────────────────────────── #
    rs_total    = fields.Integer('RS: всього',    readonly=True)
    rs_answered = fields.Integer('RS: успішних',  readonly=True)
    rs_missed   = fields.Integer('RS: б/відп',    readonly=True)
    rs_busy     = fields.Integer('RS: зайнято',   readonly=True)
    rs_minutes  = fields.Integer('RS: хвилин',    readonly=True)

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

    def action_refresh_all(self, period_date=None):
        if period_date:
            if isinstance(period_date, str):
                from datetime import datetime as dt
                today = dt.strptime(period_date, '%Y-%m-%d').date()
            else:
                today = period_date
        else:
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
        # Розбивка дзвінків: Ringostat (авто) vs ручні
        auto_call_types = self.env['mail.activity.type'].search([('name', 'in', [
            'Вихідний дзвінок', 'Вхідний дзвінок',
        ])])
        manual_call_type = self.env['mail.activity.type'].search([
            ('name', '=', 'Телефонний дзвінок Клієнту'),
        ], limit=1)
        comm_type_ids      = comm_types.ids or [0]
        meeting_type_ids   = meeting_types.ids or [0]
        auto_call_type_ids = auto_call_types.ids or [0]
        manual_call_type_id = manual_call_type.id if manual_call_type else 0

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
                ('stage_id.is_manager_pipeline', '=', True),
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

            # 2b: заплановані — є наступна активність в Pipedrive
            cr.execute("""
                SELECT COUNT(*)
                FROM crm_lead
                WHERE id = ANY(%s)
                  AND pipedrive_next_activity_date IS NOT NULL
            """, [lead_ids])
            leads_with_planned = cr.fetchone()[0]

            # 2c: прострочені завдання (next_activity_date в минулому = прострочено)
            cr.execute("""
                SELECT COUNT(*)
                FROM crm_lead
                WHERE id = ANY(%s)
                  AND pipedrive_next_activity_date IS NOT NULL
                  AND pipedrive_next_activity_date < %s
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

            # 2d: дзвінків через телефонію Ringostat (Вихідний + Вхідний)
            cr.execute("""
                SELECT COUNT(*)
                FROM mail_message
                WHERE model = 'crm.lead'
                  AND res_id = ANY(%s)
                  AND mail_activity_type_id = ANY(%s)
                  AND date >= %s AND date <= %s
            """, [lead_ids, auto_call_type_ids, first_day, last_day])
            comm_auto = cr.fetchone()[0]

            # 2e: ручних дзвінків створених самим менеджером
            cr.execute("""
                SELECT COUNT(mm.id)
                FROM mail_message mm
                JOIN res_users u ON u.partner_id = mm.author_id
                WHERE mm.model = 'crm.lead'
                  AND mm.res_id = ANY(%s)
                  AND mm.mail_activity_type_id = %s
                  AND u.id = %s
                  AND mm.date >= %s AND mm.date <= %s
            """, [lead_ids, manual_call_type_id, manager.id, first_day, last_day])
            comm_manual = cr.fetchone()[0]

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

            # RS: Ringostat дзвінки за місяць (з rayton.ringostat.call)
            cr.execute("""
                SELECT
                    COUNT(*),
                    COUNT(CASE WHEN call_status = 'ANSWERED' THEN 1 END),
                    COUNT(CASE WHEN call_status NOT IN ('ANSWERED', 'BUSY') THEN 1 END),
                    COUNT(CASE WHEN call_status = 'BUSY' THEN 1 END),
                    COALESCE(
                        SUM(CASE WHEN call_status = 'ANSWERED' THEN call_duration ELSE 0 END) / 60,
                        0
                    )
                FROM rayton_ringostat_call
                WHERE user_id = %s
                  AND call_date >= %s AND call_date <= %s
            """, [manager.id, first_day, last_day])
            rs_row      = cr.fetchone()
            rs_total    = rs_row[0] or 0
            rs_answered = rs_row[1] or 0
            rs_missed   = rs_row[2] or 0
            rs_busy     = rs_row[3] or 0
            rs_minutes  = rs_row[4] or 0

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
                'comm_total':             comm_auto + comm_manual,
                'comm_auto':              comm_auto,
                'comm_manual':            comm_manual,
                'rs_total':               rs_total,
                'rs_answered':            rs_answered,
                'rs_missed':              rs_missed,
                'rs_busy':                rs_busy,
                'rs_minutes':             rs_minutes,
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

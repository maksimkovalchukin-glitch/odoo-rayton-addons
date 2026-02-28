import re
import math
import logging
import requests
from markupsafe import Markup
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

WEBHOOK_SES = "https://n8n.rayton.net/webhook/bb30efd0-c82c-4b1e-9f5c-4a34c6a3dbe6"
WEBHOOK_UZE = "https://n8n.rayton.net/webhook/34d36afc-8cda-4ddd-9e8d-2f057e9dc620"

DC_AC_RATIO = 1.28
MIN_RATIO = 1.1
MAX_RATIO = 1.5
GENERATION_PER_100KW = 18000
MIN_AC_KW = 100
MIN_MONTHLY_MWH = 10

INVERTERS = [
    {'name': 'Huawei SUN2000-150KTL-G0', 'power': 150},
    {'name': 'Huawei SUN2000-115KTL-M2', 'power': 115},
    {'name': 'Huawei SUN2000-100KTL-M2', 'power': 100},
    {'name': 'Huawei SUN2000-50KTL-M3',  'power': 50},
    {'name': 'Huawei SUN2000-30KTL-M3',  'power': 30},
]

ROOF_COEFF_TILTED = 130.55
ROOF_COEFF_FLAT   = 229.33


def _get_module_watts_kw(module_type_text):
    m = re.search(r'(\d+)W', module_type_text or '')
    return int(m.group(1)) / 1000.0 if m else 0.0


def _round_to_50(value):
    return math.ceil(value / 50) * 50


def _select_inverters(target_ac_kw):
    sorted_inv = sorted(INVERTERS, key=lambda x: x['power'], reverse=True)
    remaining = target_ac_kw
    result = []
    for inv in sorted_inv:
        if inv['power'] >= 100:
            qty = int(remaining // inv['power'])
            if qty > 0:
                result.append({'name': inv['name'], 'power': inv['power'], 'qty': qty})
                remaining -= qty * inv['power']
    if remaining > 0:
        for inv in sorted_inv:
            if inv['power'] < 100:
                qty = math.ceil(remaining / inv['power'])
                if qty > 0:
                    result.append({'name': inv['name'], 'power': inv['power'], 'qty': qty})
                    break
    if not result:
        return None
    total_ac = sum(i['power'] * i['qty'] for i in result)
    while len(result) < 3:
        result.append({'name': '', 'power': 0, 'qty': 0})
    return {'list': result[:3], 'total_ac': total_ac}


def _build_inverter_payload(inv_result):
    slots = inv_result['list'] if inv_result else [{'name': '', 'qty': 0}] * 3
    return {
        'inverter_1_model': slots[0].get('name', ''),
        'inverter_1_qty':   slots[0].get('qty', 0),
        'inverter_2_model': slots[1].get('name', '') if len(slots) > 1 else '',
        'inverter_2_qty':   slots[1].get('qty', 0)  if len(slots) > 1 else 0,
        'inverter_3_model': slots[2].get('name', '') if len(slots) > 2 else '',
        'inverter_3_qty':   slots[2].get('qty', 0)  if len(slots) > 2 else 0,
    }


# ── Selection lists ───────────────────────────────────────────────────────────

MODULE_TYPES = [
    ('Trina 575W',                                   'Trina 575W'),
    ('Trina 580W',                                   'Trina 580W'),
    ('Trina 610W',                                   'Trina 610W'),
    ('Trina 710W',                                   'Trina 710W'),
    ('JA 625W',                                      'JA 625W'),
    ('Longi 580W',                                   'Longi 580W'),
    ('Longi 610W',                                   'Longi 610W'),
    ('Tier-1 Trina 625TSM-NE19R, потужністю 625W',   'Tier-1 Trina 625TSM-NE19R, потужністю 625W'),
    ('Tier-1 Trina 620TSM-NE19R, потужністю 620W',   'Tier-1 Trina 620TSM-NE19R, потужністю 620W'),
]

MOUNT_TYPES = [
    ('блочки',                         'блочки'),
    ('сітка',                          'сітка'),
    ('баластна сітка',                 'баластна сітка'),
    ('баластна сітка з противагою',    'баластна сітка з противагою'),
    ('гвинт-шуруп',                    'гвинт-шуруп'),
    ('схід-захід',                     'схід-захід'),
    ('схід-захід (без баласту) деш.',  'схід-захід (без баласту) деш.'),
    ('схід-захід (без баласту) дор.',  'схід-захід (без баласту) дор.'),
    ('з підйомом',                     'з підйомом'),
    ('з підйомом без баласту',         'з підйомом без баласту'),
    ('наземка',                        'наземка'),
    ('наземка схід-захід',             'наземка схід-захід'),
]

MATERIAL_TYPES = [
    ('DC та AC', 'DC та AC'),
    ('DC',       'DC'),
]

SES_TYPES = [
    ('Дахова',  'Дахова'),
    ('Наземна', 'Наземна'),
]

INVERTER_SELECTION = [
    ('Huawei SUN2000-150KTL-G0', 'Huawei SUN2000-150KTL-G0 (150 кВт)'),
    ('Huawei SUN2000-115KTL-M2', 'Huawei SUN2000-115KTL-M2 (115 кВт)'),
    ('Huawei SUN2000-100KTL-M2', 'Huawei SUN2000-100KTL-M2 (100 кВт)'),
    ('Huawei SUN2000-50KTL-M3',  'Huawei SUN2000-50KTL-M3 (50 кВт)'),
    ('Huawei SUN2000-30KTL-M3',  'Huawei SUN2000-30KTL-M3 (30 кВт)'),
]

REGIONS = [
    ('Вінницька область',         'Вінницька область'),
    ('Волинська область',         'Волинська область'),
    ('Дніпропетровська область',  'Дніпропетровська область'),
    ('Житомирська область',       'Житомирська область'),
    ('Закарпатська область',      'Закарпатська область'),
    ('Запорізька область',        'Запорізька область'),
    ('Івано-Франківська область', 'Івано-Франківська область'),
    ('м. Київ',                   'м. Київ'),
    ('Київська область',          'Київська область'),
    ('Кіровоградська область',    'Кіровоградська область'),
    ('Львівська область',         'Львівська область'),
    ('Миколаївська область',      'Миколаївська область'),
    ('Одеська область',           'Одеська область'),
    ('Полтавська область',        'Полтавська область'),
    ('Рівненська область',        'Рівненська область'),
    ('Сумська область',           'Сумська область'),
    ('Тернопільська область',     'Тернопільська область'),
    ('Харківська область',        'Харківська область'),
    ('Херсонська область',        'Херсонська область'),
    ('Хмельницька область',       'Хмельницька область'),
    ('Черкаська область',         'Черкаська область'),
    ('Чернівецька область',       'Чернівецька область'),
    ('Чернігівська область',      'Чернігівська область'),
]

UZE_MODELS = [
    ('RESS-100-215 Режим off-grid (авт. шовний) з контролером',
     'RESS-100-215 Режим off-grid (авт. шовний) з контролером'),
    ('RESS-100-215 Режим off-grid (ручний) без контролера',
     'RESS-100-215 Режим off-grid (ручний) без контролера'),
    ('RESS-125-241 (з контролером)',  'RESS-125-241 (з контролером)'),
    ('RESS-125-241 (без контролера)', 'RESS-125-241 (без контролера)'),
    ('RESS-1125-2170 Режим off-grid (шовний)',    'RESS-1125-2170 Режим off-grid (шовний)'),
    ('RESS-1125-2170 Режим off-grid (безшовний)', 'RESS-1125-2170 Режим off-grid (безшовний)'),
    ('RESS-100-233L',  'RESS-100-233L'),
    ('RESS-80-241',    'RESS-80-241'),
    ('RESS-2500-5015', 'RESS-2500-5015'),
    ('RESS-1000-4180', 'RESS-1000-4180'),
    ('RESS-1250-4180', 'RESS-1250-4180'),
    ('RESS-1500-4180', 'RESS-1500-4180'),
    ('RESS-1000-5015', 'RESS-1000-5015'),
    ('RESS-1250-5015', 'RESS-1250-5015'),
    ('RESS-1500-5015', 'RESS-1500-5015'),
    ('RESS-1725-3344', 'RESS-1725-3344'),
    ('RESS-125-257',   'RESS-125-257'),
    ('RESS-1000-3344', 'RESS-1000-3344'),
    ('RESS-1250-3344', 'RESS-1250-3344'),
    ('RESS-1500-3344', 'RESS-1500-3344'),
    ('RESS-1725-4180', 'RESS-1725-4180'),
    ('RESS-2000-4180', 'RESS-2000-4180'),
    ('RESS-1725-5015', 'RESS-1725-5015'),
    ('RESS-500-1000 лише off-grid', 'RESS-500-1000 лише off-grid'),
    ('RESS-100-241',   'RESS-100-241'),
    ('RESS-50-241',    'RESS-50-241'),
    ('RESS-60-241',    'RESS-60-241'),
    ('RESS-125-261 Режим off-grid (не швидкий) без STS',
     'RESS-125-261 Режим off-grid (не швидкий) без STS'),
    ('RESS-125-261 Режим off-grid (швидкий) з STS',
     'RESS-125-261 Режим off-grid (швидкий) з STS'),
]

UZE_MODEL_LIMITS = {
    'RESS-100-215 Режим off-grid (авт. шовний) з контролером': 5,
    'RESS-125-241 (з контролером)': 5,
    'RESS-125-241 (без контролера)': 5,
    'RESS-100-233L': 1,
    'RESS-80-241': 1,
    'RESS-2500-5015': 50,
    'RESS-1000-4180': 50,
    'RESS-1125-2170 Режим off-grid (шовний)': 1,
    'RESS-1125-2170 Режим off-grid (безшовний)': 1,
    'RESS-100-215 Режим off-grid (ручний) без контролера': 5,
    'RESS-1250-4180': 50,
    'RESS-1500-4180': 50,
    'RESS-1250-5015': 50,
    'RESS-1500-5015': 50,
    'RESS-1000-5015': 50,
    'RESS-1725-3344': 50,
}


# ── Model ─────────────────────────────────────────────────────────────────────

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ── Status ────────────────────────────────────────────────────────────────
    kp_state = fields.Selection([
        ('none',    'Не сформовано'),
        ('pending', 'Формується...'),
        ('done',    'КП готова'),
    ], default='none', string='Статус КП', tracking=True)

    # ── Common ────────────────────────────────────────────────────────────────
    kp_type = fields.Selection([
        ('ses', '☀️ СЕС — Сонячна електростанція'),
        ('uze', '🔋 УЗЕ — Установка зберігання енергії'),
    ], string='Тип КП', default='ses')

    kp_project_name = fields.Char(string='Назва проєкту')
    kp_manager_id   = fields.Many2one('res.users', string='Менеджер')
    kp_region       = fields.Selection(REGIONS, string='Регіон')
    kp_currency     = fields.Selection([('USD', 'USD'), ('EUR', 'EUR')],
                                       string='Валюта КП', default='USD')

    # ── СЕС ──────────────────────────────────────────────────────────────────
    kp_ses_mode = fields.Selection([
        ('consumption', '📊 За споживанням клієнта (МВт·год/міс)'),
        ('power',       '⚡ Планова потужність СЕС (кВт DC)'),
        ('roof',        '🏠 За площею даху (М²)'),
        ('manual',      '✍️ Внести дані вручну'),
    ], string='Режим розрахунку', default='consumption')

    kp_module_type    = fields.Selection(MODULE_TYPES,   string='Тип панелей')
    kp_mount_type     = fields.Selection(MOUNT_TYPES,    string='Тип монтажу')
    kp_material_type  = fields.Selection(MATERIAL_TYPES, string='Матеріали', default='DC та AC')
    kp_ses_type       = fields.Selection(SES_TYPES,      string='Тип СЕС',   default='Дахова')
    kp_power_reg      = fields.Char(
        string='Регулювання потужності',
        default='Лічильник + Трансформатори струму (3шт)',
    )
    kp_monitoring     = fields.Char(
        string='Пристрій моніторингу',
        default='Huawei Smart Dongle',
    )
    kp_price_vat_type = fields.Char(string='Ціна (ПДВ)', default='з ПДВ')
    kp_price_per_kw   = fields.Float(string='Ціна за кВт', digits=(10, 2))

    kp_monthly_consumption = fields.Float(string='Місячне споживання (МВт·год/міс)', digits=(10, 2))
    kp_planned_dc_power    = fields.Float(string='Планова потужність DC (кВт)',       digits=(10, 2))
    kp_roof_area           = fields.Float(string='Площа даху (М²)',                   digits=(10, 2))
    kp_roof_mount_type     = fields.Selection([
        ('tilted', 'Похилий дах (130.55 Вт/М²)'),
        ('flat',   'Плоский дах (229.33 Вт/М²)'),
    ], string='Тип даху', default='tilted')

    kp_inv1_model = fields.Selection(INVERTER_SELECTION, string='Інвертор 1')
    kp_inv1_qty   = fields.Integer(string='Кількість 1', default=0)
    kp_inv2_model = fields.Selection(INVERTER_SELECTION, string='Інвертор 2')
    kp_inv2_qty   = fields.Integer(string='Кількість 2', default=0)
    kp_inv3_model = fields.Selection(INVERTER_SELECTION, string='Інвертор 3')
    kp_inv3_qty   = fields.Integer(string='Кількість 3', default=0)
    kp_panel_qty  = fields.Integer(string='Кількість панелей', default=0)

    kp_manual_dc_info = fields.Char(
        string='Потужність DC',
        compute='_compute_kp_manual_dc_info',
        store=False,
    )
    kp_manual_ratio_info = fields.Char(
        string='DC/AC розрахунок',
        compute='_compute_kp_manual_ratio',
        store=False,
    )

    # ── УЗЕ ──────────────────────────────────────────────────────────────────
    kp_uze_model     = fields.Selection(UZE_MODELS, string='Модель УЗЕ')
    kp_uze_qty       = fields.Integer(string='Кількість (1–50)', default=1)
    kp_uze_vat       = fields.Selection([('без ПДВ', 'без ПДВ'), ('з ПДВ', 'з ПДВ')],
                                        string='Вартість УЗЕ', default='без ПДВ')
    kp_equipment_vat = fields.Selection([('з ПДВ', 'з ПДВ'), ('без ПДВ', 'без ПДВ')],
                                        string='Обладнання та матеріали', default='з ПДВ')
    kp_usage_type    = fields.Selection([
        ('На власне споживання',     'На власне споживання'),
        ('Арбітраж на підприємстві', 'Арбітраж на підприємстві'),
    ], string='Тип використання', default='На власне споживання')
    kp_delivery_term = fields.Selection([
        ('1 місяць',      '1 місяць'),
        ('2 місяці',      '2 місяці'),
        ('3 місяці',      '3 місяці'),
        ('3–4 місяці',    '3–4 місяці'),
        ('3,5–4 місяці',  '3,5–4 місяці'),
        ('4–4,5 місяця',  '4–4,5 місяця'),
        ('4–5 місяців',   '4–5 місяців'),
        ('5 місяців',     '5 місяців'),
        ('4,5–6 місяців', '4,5–6 місяців'),
    ], string='Термін доставки', default='3 місяці')
    kp_payment_terms = fields.Selection([
        ('100% передплата',
         '100% передплата'),
        ('30% аванс, 70% перед відвантаженням з заводу',
         '30% аванс, 70% перед відвантаженням з заводу'),
    ], string='Умови оплати', default='100% передплата')
    kp_delivery_terms = fields.Selection([
        ("DAP. Доставка до об'єкту Замовника без послуг по розвантаженню",
         "DAP. Доставка до об'єкту Замовника без послуг по розвантаженню"),
    ], string='Умови поставки',
        default="DAP. Доставка до об'єкту Замовника без послуг по розвантаженню")

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends('kp_panel_qty', 'kp_module_type', 'kp_ses_mode')
    def _compute_kp_manual_dc_info(self):
        for rec in self:
            if rec.kp_ses_mode != 'manual':
                rec.kp_manual_dc_info = ''
                continue
            module_kw = _get_module_watts_kw(rec.kp_module_type or '')
            if rec.kp_panel_qty and module_kw:
                dc = rec.kp_panel_qty * module_kw
                ac_min = dc / MAX_RATIO   # при DC/AC = 1.5
                ac_max = dc / MIN_RATIO   # при DC/AC = 1.1
                ac_opt = dc / DC_AC_RATIO # оптимальне
                rec.kp_manual_dc_info = (
                    f'⚡  DC: {dc:.2f} кВт  |  '
                    f'Потрібне AC: {ac_min:.0f} – {ac_max:.0f} кВт  '
                    f'(оптим. ~{ac_opt:.0f} кВт)'
                )
            else:
                rec.kp_manual_dc_info = 'Оберіть тип панелей та кількість'

    @api.depends(
        'kp_inv1_model', 'kp_inv1_qty',
        'kp_inv2_model', 'kp_inv2_qty',
        'kp_inv3_model', 'kp_inv3_qty',
        'kp_panel_qty', 'kp_module_type', 'kp_ses_mode',
    )
    def _compute_kp_manual_ratio(self):
        inv_map = {i['name']: i['power'] for i in INVERTERS}
        for rec in self:
            if rec.kp_ses_mode != 'manual':
                rec.kp_manual_ratio_info = ''
                continue

            def pwr(model, qty):
                return inv_map.get(model, 0) * qty if model else 0

            real_ac = (
                pwr(rec.kp_inv1_model, rec.kp_inv1_qty) +
                pwr(rec.kp_inv2_model, rec.kp_inv2_qty) +
                pwr(rec.kp_inv3_model, rec.kp_inv3_qty)
            )
            module_kw = _get_module_watts_kw(rec.kp_module_type)
            real_dc = rec.kp_panel_qty * module_kw if module_kw else 0.0

            if real_ac > 0 and real_dc > 0:
                ratio = real_dc / real_ac
                status = '✅' if MIN_RATIO <= ratio <= MAX_RATIO else '⚠️ поза нормою!'
                rec.kp_manual_ratio_info = (
                    f'{status}  DC: {real_dc:.2f} кВт  |  AC: {real_ac:.0f} кВт  |  '
                    f'DC/AC = {ratio:.2f}  (норма {MIN_RATIO}–{MAX_RATIO})'
                )
            elif real_dc > 0:
                rec.kp_manual_ratio_info = (
                    f'⚡ DC: {real_dc:.2f} кВт  |  Оберіть інвертори для перевірки DC/AC'
                )
            elif real_ac > 0:
                rec.kp_manual_ratio_info = (
                    f'AC: {real_ac:.0f} кВт  |  Вкажіть кількість панелей'
                )
            else:
                rec.kp_manual_ratio_info = 'Оберіть панелі, кількість та інвертори'

    @api.onchange('partner_id')
    def _onchange_partner_kp_name(self):
        if self.partner_id and not self.kp_project_name:
            self.kp_project_name = self.partner_id.name

    @api.onchange('user_id')
    def _onchange_user_kp_manager(self):
        if self.user_id and not self.kp_manager_id:
            self.kp_manager_id = self.user_id

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _kp_get_opportunity(self):
        """Return linked CRM lead/opportunity, or None.
        Safe: checks field existence so module works without sale_crm."""
        self.ensure_one()
        if 'opportunity_id' in self._fields:
            return self.opportunity_id or None
        return None

    def _kp_post_to_lead(self, lead, body):
        """Post a message to the CRM lead referencing this sale order."""
        lead.message_post(
            body=Markup('{} (<a href="/odoo/sales/{}">{}</a>)').format(
                Markup(body), self.id, self.name
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    # ── Generate action ───────────────────────────────────────────────────────

    def action_generate_kp(self):
        self.ensure_one()

        if self.kp_type == 'ses':
            payload = self._kp_build_ses_payload()
            webhook_url = WEBHOOK_SES
        else:
            payload = self._kp_build_uze_payload()
            webhook_url = WEBHOOK_UZE

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        payload.update({
            'sale_order_id':   self.id,
            'sale_order_name': self.name,
            'callback_url':    f'{base_url}/rayton/kp/callback',
            'kp_type':         self.kp_type,
        })

        try:
            resp = requests.post(webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            _logger.error("[rayton_sale_kp] Webhook error: %s", e)
            raise UserError(f'Помилка надсилання на n8n: {e}')

        kp_label = dict(self._fields['kp_type'].selection)[self.kp_type]
        self.kp_state = 'pending'
        self.message_post(
            body=(
                f'📤 КП запущено в генерацію ({kp_label}). '
                f'PDF буде додано автоматично.'
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Mirror to linked CRM opportunity
        lead = self._kp_get_opportunity()
        if lead:
            self._kp_post_to_lead(
                lead,
                f'📤 КП запущено в генерацію ({kp_label}). PDF буде додано автоматично.',
            )

    # ── SES builders ──────────────────────────────────────────────────────────

    def _kp_build_ses_payload(self):
        mode = self.kp_ses_mode
        module_kw = _get_module_watts_kw(self.kp_module_type)

        if mode == 'consumption':
            data = self._kp_calc_consumption(module_kw)
        elif mode == 'power':
            data = self._kp_calc_power(module_kw)
        elif mode == 'roof':
            data = self._kp_calc_roof(module_kw)
        else:
            data = self._kp_calc_manual()

        data.update({
            'calculation_mode':  mode,
            'project_name':      self.kp_project_name or '',
            'manager':           self.kp_manager_id.name or '',
            'region':            self.kp_region or '',
            'module_type':       self.kp_module_type or '',
            'mount_type':        self.kp_mount_type or '',
            'material_type':     self.kp_material_type or '',
            'ses_type':          self.kp_ses_type or '',
            'power_regulation':  self.kp_power_reg or '',
            'monitoring_device': self.kp_monitoring or '',
            'currency':          self.kp_currency or 'USD',
            'price_vat_type':    self.kp_price_vat_type or '',
            'price_per_kw':      str(self.kp_price_per_kw),
        })
        return data

    def _kp_calc_consumption(self, module_kw):
        mwh = self.kp_monthly_consumption
        if mwh < MIN_MONTHLY_MWH:
            raise UserError(f'Місячне споживання має бути не менше {MIN_MONTHLY_MWH} МВт·год.')
        target_ac = max(_round_to_50((mwh * 1000 / GENERATION_PER_100KW) * 100), MIN_AC_KW)
        inv = _select_inverters(target_ac)
        if not inv:
            raise UserError('Не вдалося підібрати інвертори.')
        real_ac = inv['total_ac']
        real_dc = real_ac * DC_AC_RATIO
        panel_qty = math.ceil(real_dc / module_kw) if module_kw else 0
        return {
            'monthly_consumption_mwh': mwh,
            'real_dc': f'{real_dc:.2f}', 'real_ac': f'{real_ac:.2f}',
            'panel_qty': panel_qty, **_build_inverter_payload(inv),
        }

    def _kp_calc_power(self, module_kw):
        dc = self.kp_planned_dc_power
        if dc <= 0:
            raise UserError('Вкажіть планову потужність DC (кВт).')
        target_ac = max(_round_to_50(dc / DC_AC_RATIO), MIN_AC_KW)
        inv = _select_inverters(target_ac)
        if not inv:
            raise UserError('Не вдалося підібрати інвертори.')
        real_ac = inv['total_ac']
        real_dc = real_ac * DC_AC_RATIO
        panel_qty = math.ceil(real_dc / module_kw) if module_kw else 0
        return {
            'planned_dc_power': dc,
            'real_dc': f'{real_dc:.2f}', 'real_ac': f'{real_ac:.2f}',
            'panel_qty': panel_qty, **_build_inverter_payload(inv),
        }

    def _kp_calc_roof(self, module_kw):
        area = self.kp_roof_area
        if area <= 0:
            raise UserError('Вкажіть площу даху (М²).')
        coeff = ROOF_COEFF_FLAT if self.kp_roof_mount_type == 'flat' else ROOF_COEFF_TILTED
        dc_kw = (area * coeff) / 1000.0
        target_ac = max(_round_to_50(dc_kw / DC_AC_RATIO), MIN_AC_KW)
        inv = _select_inverters(target_ac)
        if not inv:
            raise UserError('Не вдалося підібрати інвертори.')
        real_ac = inv['total_ac']
        real_dc = real_ac * DC_AC_RATIO
        panel_qty = math.ceil(real_dc / module_kw) if module_kw else 0
        return {
            'roof_area': area, 'roof_mount_type': self.kp_roof_mount_type,
            'real_dc': f'{real_dc:.2f}', 'real_ac': f'{real_ac:.2f}',
            'panel_qty': panel_qty, **_build_inverter_payload(inv),
        }

    def _kp_calc_manual(self):
        inv_map = {i['name']: i['power'] for i in INVERTERS}

        def pwr(model, qty):
            return inv_map.get(model, 0) * qty if model else 0

        real_ac = (
            pwr(self.kp_inv1_model, self.kp_inv1_qty) +
            pwr(self.kp_inv2_model, self.kp_inv2_qty) +
            pwr(self.kp_inv3_model, self.kp_inv3_qty)
        )
        if real_ac < 30:
            raise UserError('Загальна AC потужність інверторів має бути не менше 30 кВт.')
        module_kw = _get_module_watts_kw(self.kp_module_type)
        real_dc = self.kp_panel_qty * module_kw if module_kw else 0.0
        if real_ac > 0 and real_dc > 0:
            ratio = real_dc / real_ac
            if not (MIN_RATIO <= ratio <= MAX_RATIO):
                raise UserError(f'DC/AC = {ratio:.2f} — виходить за норму ({MIN_RATIO}–{MAX_RATIO}).')
        return {
            'real_dc': f'{real_dc:.2f}', 'real_ac': f'{real_ac:.2f}',
            'panel_qty': self.kp_panel_qty,
            'inverter_1_model': self.kp_inv1_model or '', 'inverter_1_qty': self.kp_inv1_qty,
            'inverter_2_model': self.kp_inv2_model or '', 'inverter_2_qty': self.kp_inv2_qty,
            'inverter_3_model': self.kp_inv3_model or '', 'inverter_3_qty': self.kp_inv3_qty,
        }

    # ── UZE builder ───────────────────────────────────────────────────────────

    def _kp_build_uze_payload(self):
        max_qty = UZE_MODEL_LIMITS.get(self.kp_uze_model)
        if max_qty and self.kp_uze_qty > max_qty:
            raise UserError(f'Для моделі "{self.kp_uze_model}" max кількість: {max_qty}.')
        return {
            'project_name':   self.kp_project_name or '',
            'manager':        self.kp_manager_id.name or '',
            'region':         self.kp_region or '',
            'uze_model':      self.kp_uze_model or '',
            'uze_qty':        self.kp_uze_qty,
            'uze_vat':        self.kp_uze_vat or '',
            'equipment_vat':  self.kp_equipment_vat or '',
            'currency':       self.kp_currency or 'USD',
            'usage_type':     self.kp_usage_type or '',
            'delivery_term':  self.kp_delivery_term or '',
            'payment_terms':  self.kp_payment_terms or '',
            'delivery_terms': self.kp_delivery_terms or '',
        }

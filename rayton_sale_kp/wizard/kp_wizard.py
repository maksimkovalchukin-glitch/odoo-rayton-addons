import math
import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Constants (mirrors Telegram webapp js) ────────────────────────────────────

WEBHOOK_SES = "https://n8n.rayton.net/webhook/bb30efd0-c82c-4b1e-9f5c-4a34c6a3dbe6"
WEBHOOK_UZE = "https://n8n.rayton.net/webhook/34d36afc-8cda-4ddd-9e8d-2f057e9dc620"

DC_AC_RATIO = 1.28
MIN_RATIO = 1.1
MAX_RATIO = 1.5
GENERATION_PER_100KW = 18000   # kWh/year per 100 kW AC
MIN_AC_KW = 100                 # minimum AC power
MIN_MONTHLY_MWH = 10

INVERTERS = [
    {'name': 'Huawei SUN2000-150KTL-G0', 'power': 150},
    {'name': 'Huawei SUN2000-115KTL-M2', 'power': 115},
    {'name': 'Huawei SUN2000-100KTL-M2', 'power': 100},
    {'name': 'Huawei SUN2000-50KTL-M3',  'power': 50},
    {'name': 'Huawei SUN2000-30KTL-M3',  'power': 30},
]

# Roof area → DC power coefficients (W/m²)
ROOF_COEFF_TILTED = 130.55
ROOF_COEFF_FLAT   = 229.33

# UZE model max qty limits (0 = unlimited/на замовлення)
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

REGIONS = [
    ('Вінницька область', 'Вінницька область'),
    ('Волинська область', 'Волинська область'),
    ('Дніпропетровська область', 'Дніпропетровська область'),
    ('Житомирська область', 'Житомирська область'),
    ('Закарпатська область', 'Закарпатська область'),
    ('Запорізька область', 'Запорізька область'),
    ('Івано-Франківська область', 'Івано-Франківська область'),
    ('м. Київ', 'м. Київ'),
    ('Київська область', 'Київська область'),
    ('Кіровоградська область', 'Кіровоградська область'),
    ('Львівська область', 'Львівська область'),
    ('Миколаївська область', 'Миколаївська область'),
    ('Одеська область', 'Одеська область'),
    ('Полтавська область', 'Полтавська область'),
    ('Рівненська область', 'Рівненська область'),
    ('Сумська область', 'Сумська область'),
    ('Тернопільська область', 'Тернопільська область'),
    ('Харківська область', 'Харківська область'),
    ('Херсонська область', 'Херсонська область'),
    ('Хмельницька область', 'Хмельницька область'),
    ('Черкаська область', 'Черкаська область'),
    ('Чернівецька область', 'Чернівецька область'),
    ('Чернігівська область', 'Чернігівська область'),
]

MODULE_TYPES = [
    ('575', 'Trina Vertex S+ 575W'),
    ('580', 'Trina Vertex S+ 580W'),
    ('585', 'Trina Vertex S+ 585W'),
    ('590', 'Trina Vertex S+ 590W'),
    ('595', 'Trina Vertex S+ 595W'),
    ('600', 'Trina Vertex S+ 600W'),
    ('605', 'JA Solar Deep Blue 605W'),
    ('610', 'JA Solar Deep Blue 610W'),
    ('615', 'JA Solar Deep Blue 615W'),
    ('620', 'JA Solar Deep Blue 620W'),
    ('625', 'JA Solar Deep Blue 625W'),
    ('630', 'Longi Hi-MO 6 630W'),
    ('635', 'Longi Hi-MO 6 635W'),
    ('640', 'Longi Hi-MO 6 640W'),
    ('645', 'Longi Hi-MO 6 645W'),
    ('650', 'Longi Hi-MO 6 650W'),
    ('655', 'Longi Hi-MO 6 655W'),
    ('660', 'Longi Hi-MO 6 660W'),
    ('665', 'Longi Hi-MO 6 665W'),
    ('670', 'Longi Hi-MO 6 670W'),
    ('680', 'Longi Hi-MO 6 680W'),
    ('695', 'Longi Hi-MO 6 695W'),
    ('710', 'Longi Hi-MO 6 710W'),
]

MOUNT_TYPES = [
    ('Стаціонарна конструкція з нахилом 20°', 'Стаціонарна конструкція з нахилом 20°'),
    ('Стаціонарна конструкція з нахилом 25°', 'Стаціонарна конструкція з нахилом 25°'),
    ('Стаціонарна конструкція з нахилом 30°', 'Стаціонарна конструкція з нахилом 30°'),
    ('Горизонтальна конструкція (плоский дах)', 'Горизонтальна конструкція (плоский дах)'),
    ('Двовісний трекер', 'Двовісний трекер'),
    ('Одновісний трекер', 'Одновісний трекер'),
]

MATERIAL_TYPES = [
    ('Алюміній', 'Алюміній'),
    ('Оцинкована сталь', 'Оцинкована сталь'),
    ('Нержавіюча сталь', 'Нержавіюча сталь'),
]

SES_TYPES = [
    ('Наземна', 'Наземна'),
    ('Дахова', 'Дахова'),
    ('Паркінг/навіс', 'Паркінг/навіс'),
    ('Плавуча', 'Плавуча'),
]

UZE_MODELS = [
    ('RESS-100-215 Режим off-grid (авт. шовний) з контролером',
     'RESS-100-215 Режим off-grid (авт. шовний) з контролером'),
    ('RESS-100-215 Режим off-grid (ручний) без контролера',
     'RESS-100-215 Режим off-grid (ручний) без контролера'),
    ('RESS-125-241 (з контролером)', 'RESS-125-241 (з контролером)'),
    ('RESS-125-241 (без контролера)', 'RESS-125-241 (без контролера)'),
    ('RESS-1125-2170 Режим off-grid (шовний)', 'RESS-1125-2170 Режим off-grid (шовний)'),
    ('RESS-1125-2170 Режим off-grid (безшовний)', 'RESS-1125-2170 Режим off-grid (безшовний)'),
    ('RESS-100-233L', 'RESS-100-233L'),
    ('RESS-80-241', 'RESS-80-241'),
    ('RESS-2500-5015', 'RESS-2500-5015'),
    ('RESS-1000-4180', 'RESS-1000-4180'),
    ('RESS-1250-4180', 'RESS-1250-4180'),
    ('RESS-1500-4180', 'RESS-1500-4180'),
    ('RESS-1000-5015', 'RESS-1000-5015'),
    ('RESS-1250-5015', 'RESS-1250-5015'),
    ('RESS-1500-5015', 'RESS-1500-5015'),
    ('RESS-1725-3344', 'RESS-1725-3344'),
    ('RESS-125-257', 'RESS-125-257'),
    ('RESS-1000-3344', 'RESS-1000-3344'),
    ('RESS-1250-3344', 'RESS-1250-3344'),
    ('RESS-1500-3344', 'RESS-1500-3344'),
    ('RESS-1725-4180', 'RESS-1725-4180'),
    ('RESS-2000-4180', 'RESS-2000-4180'),
    ('RESS-1725-5015', 'RESS-1725-5015'),
    ('RESS-500-1000 лише off-grid', 'RESS-500-1000 лише off-grid'),
    ('RESS-100-241', 'RESS-100-241'),
    ('RESS-50-241', 'RESS-50-241'),
    ('RESS-60-241', 'RESS-60-241'),
    ('RESS-125-261 Режим off-grid (не швидкий) без STS',
     'RESS-125-261 Режим off-grid (не швидкий) без STS'),
    ('RESS-125-261 Режим off-grid (швидкий) з STS',
     'RESS-125-261 Режим off-grid (швидкий) з STS'),
]

INVERTER_SELECTION = [
    ('Huawei SUN2000-150KTL-G0', 'Huawei SUN2000-150KTL-G0 (150 кВт)'),
    ('Huawei SUN2000-115KTL-M2', 'Huawei SUN2000-115KTL-M2 (115 кВт)'),
    ('Huawei SUN2000-100KTL-M2', 'Huawei SUN2000-100KTL-M2 (100 кВт)'),
    ('Huawei SUN2000-50KTL-M3',  'Huawei SUN2000-50KTL-M3 (50 кВт)'),
    ('Huawei SUN2000-30KTL-M3',  'Huawei SUN2000-30KTL-M3 (30 кВт)'),
]


# ── Helper functions (Python port of webapp JS) ───────────────────────────────

def _round_to_50(value):
    return math.ceil(value / 50) * 50


def _select_inverters(target_ac_kw):
    """Greedy inverter selection: fill with largest (>=100kW) first, remainder with smaller."""
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

    # Pad to 3 slots
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


# ── Wizard model ──────────────────────────────────────────────────────────────

class KpGenerateWizard(models.TransientModel):
    _name = 'kp.generate.wizard'
    _description = 'Генератор комерційної пропозиції'

    # ── Common ────────────────────────────────────────────────────────────────
    sale_order_id = fields.Many2one('sale.order', string='Пропозиція', readonly=True, required=True)
    kp_type = fields.Selection([
        ('ses', '☀️ СЕС — Сонячна електростанція'),
        ('uze', '🔋 УЗЕ — Установка зберігання енергії'),
    ], string='Тип КП', required=True, default='ses')
    project_name = fields.Char(string='Назва проєкту', required=True)
    manager = fields.Char(string='Менеджер', required=True)
    region = fields.Selection(REGIONS, string='Регіон', required=True)
    currency_kp = fields.Selection([('USD', 'USD'), ('EUR', 'EUR')],
                                   string='Валюта', default='USD', required=True)

    # ── СЕС ──────────────────────────────────────────────────────────────────
    ses_mode = fields.Selection([
        ('consumption', '📊 За споживанням клієнта (МВт·год/міс)'),
        ('power',       '⚡ Планова потужність СЕС (кВт DC)'),
        ('roof',        '🏠 За площею даху (М²)'),
        ('manual',      '✍️ Внести дані вручну'),
    ], string='Режим розрахунку', default='consumption')

    module_type = fields.Selection(MODULE_TYPES, string='Тип сонячних панелей')
    mount_type = fields.Selection(MOUNT_TYPES, string='Тип монтажу')
    material_type = fields.Selection(MATERIAL_TYPES, string='Матеріал конструкції')
    ses_type = fields.Selection(SES_TYPES, string='Тип СЕС')
    power_regulation = fields.Selection([
        ('ДСТУ-Н Б В.2.5-44:2011 (МСЕЕ 364-4-43:2001)', 'ДСТУ-Н Б В.2.5-44:2011'),
    ], string='Регулювання потужності',
        default='ДСТУ-Н Б В.2.5-44:2011 (МСЕЕ 364-4-43:2001)')
    monitoring_device = fields.Selection([
        ('Huawei Smart Dongle', 'Huawei Smart Dongle'),
    ], string='Пристрій моніторингу', default='Huawei Smart Dongle')
    price_vat_type = fields.Selection([
        ('з ПДВ', 'з ПДВ'),
        ('без ПДВ', 'без ПДВ'),
    ], string='Ціна (ПДВ)', default='без ПДВ')
    price_per_kw = fields.Float(string='Ціна за кВт (без монтажу)', digits=(10, 2))

    # Consumption mode
    monthly_consumption = fields.Float(string='Місячне споживання (МВт·год/міс)', digits=(10, 2))

    # Power mode
    planned_dc_power = fields.Float(string='Планова потужність DC (кВт)', digits=(10, 2))

    # Roof mode
    roof_area = fields.Float(string='Площа даху (М²)', digits=(10, 2))
    roof_mount_type = fields.Selection([
        ('tilted', 'Похилий дах (130.55 Вт/М²)'),
        ('flat',   'Плоский дах (229.33 Вт/М²)'),
    ], string='Тип даху', default='tilted')

    # Manual mode
    inverter_1_model = fields.Selection(INVERTER_SELECTION, string='Інвертор 1')
    inverter_1_qty   = fields.Integer(string='Кількість 1', default=0)
    inverter_2_model = fields.Selection(INVERTER_SELECTION, string='Інвертор 2')
    inverter_2_qty   = fields.Integer(string='Кількість 2', default=0)
    inverter_3_model = fields.Selection(INVERTER_SELECTION, string='Інвертор 3')
    inverter_3_qty   = fields.Integer(string='Кількість 3', default=0)
    panel_qty_manual = fields.Integer(string='Кількість панелей', default=0)

    # ── УЗЕ ──────────────────────────────────────────────────────────────────
    uze_model = fields.Selection(UZE_MODELS, string='Модель УЗЕ')
    uze_qty = fields.Integer(string='Кількість УЗЕ', default=1)
    uze_vat = fields.Selection([
        ('без ПДВ', 'без ПДВ'),
        ('з ПДВ',   'з ПДВ'),
    ], string='Вартість УЗЕ', default='без ПДВ')
    equipment_vat = fields.Selection([
        ('з ПДВ',   'з ПДВ'),
        ('без ПДВ', 'без ПДВ'),
    ], string='Обладнання та матеріали', default='з ПДВ')
    usage_type = fields.Selection([
        ('На власне споживання', 'На власне споживання'),
        ('Арбітраж на підприємстві', 'Арбітраж на підприємстві'),
    ], string='Тип використання', default='На власне споживання')
    delivery_term = fields.Selection([
        ('1 місяць',         '1 місяць'),
        ('2 місяці',         '2 місяці'),
        ('3 місяці',         '3 місяці'),
        ('3–4 місяці',       '3–4 місяці'),
        ('3,5–4 місяці',     '3,5–4 місяці'),
        ('4–4,5 місяця',     '4–4,5 місяця'),
        ('4–5 місяців',      '4–5 місяців'),
        ('5 місяців',        '5 місяців'),
        ('4,5–6 місяців',    '4,5–6 місяців'),
    ], string='Термін доставки', default='3 місяці')
    payment_terms_kp = fields.Selection([
        ('100% передплата',                                    '100% передплата'),
        ('30% аванс, 70% перед відвантаженням з заводу',
         '30% аванс, 70% перед відвантаженням з заводу'),
    ], string='Умови оплати', default='100% передплата')
    delivery_terms = fields.Selection([
        ("DAP. Доставка до об'єкту Замовника без послуг по розвантаженню",
         "DAP. Доставка до об'єкту Замовника без послуг по розвантаженню"),
    ], string='Умови поставки',
        default="DAP. Доставка до об'єкту Замовника без послуг по розвантаженню")

    # ── Calculation results (display only) ───────────────────────────────────
    calc_info = fields.Text(string='Результат розрахунку', readonly=True)

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_generate(self):
        self.ensure_one()
        order = self.sale_order_id

        if self.kp_type == 'ses':
            payload = self._build_ses_payload()
            webhook_url = WEBHOOK_SES
        else:
            payload = self._build_uze_payload()
            webhook_url = WEBHOOK_UZE

        # Add common meta fields
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        payload.update({
            'sale_order_id': order.id,
            'sale_order_name': order.name,
            'callback_url': f'{base_url}/rayton/kp/callback',
            'kp_type': self.kp_type,
        })

        # Send to n8n
        try:
            resp = requests.post(webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            _logger.error("[rayton_sale_kp] Webhook error: %s", e)
            raise UserError(
                f'Помилка надсилання на n8n: {e}\n'
                f'Перевірте підключення до інтернету та налаштування n8n.'
            )

        # Mark as pending
        order.kp_state = 'pending'
        order.message_post(
            body=f'📤 КП запущено в генерацію ({dict(self._fields["kp_type"].selection)[self.kp_type]}). '
                 f'PDF буде додано автоматично.',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return {'type': 'ir.actions.act_window_close'}

    # ── SES payload builders ──────────────────────────────────────────────────

    def _build_ses_payload(self):
        """Build payload and run calculations based on ses_mode."""
        mode = self.ses_mode
        module_power_kw = int(self.module_type or 0) / 1000.0 if self.module_type else 0

        if mode == 'consumption':
            payload = self._calc_consumption(module_power_kw)
        elif mode == 'power':
            payload = self._calc_power(module_power_kw)
        elif mode == 'roof':
            payload = self._calc_roof(module_power_kw)
        else:  # manual
            payload = self._calc_manual()

        # Common SES fields
        payload.update({
            'calculation_mode': mode,
            'project_name':     self.project_name,
            'manager':          self.manager,
            'region':           self.region,
            'module_type':      dict(MODULE_TYPES).get(self.module_type, ''),
            'mount_type':       self.mount_type or '',
            'material_type':    self.material_type or '',
            'ses_type':         self.ses_type or '',
            'power_regulation': self.power_regulation or '',
            'monitoring_device': self.monitoring_device or '',
            'currency':         self.currency_kp,
            'price_vat_type':   self.price_vat_type or '',
            'price_per_kw':     str(self.price_per_kw),
        })
        return payload

    def _calc_consumption(self, module_power_kw):
        """consumption mode: monthly MWh → target AC → inverters → panels."""
        monthly_mwh = self.monthly_consumption
        if monthly_mwh < MIN_MONTHLY_MWH:
            raise UserError(f'Місячне споживання має бути не менше {MIN_MONTHLY_MWH} МВт·год.')

        monthly_kwh = monthly_mwh * 1000
        target_ac = _round_to_50((monthly_kwh / GENERATION_PER_100KW) * 100)
        target_ac = max(target_ac, MIN_AC_KW)

        inv_result = _select_inverters(target_ac)
        if not inv_result:
            raise UserError('Не вдалося підібрати інвертори для заданого споживання.')

        real_ac = inv_result['total_ac']
        real_dc = real_ac * DC_AC_RATIO
        panel_qty = math.ceil(real_dc / module_power_kw) if module_power_kw else 0

        self.calc_info = (
            f'Режим: за споживанням | Споживання: {monthly_mwh} МВт·год/міс\n'
            f'Цільова AC: {target_ac} кВт | Реальна AC: {real_ac} кВт | DC: {round(real_dc, 2)} кВт\n'
            f'Панелей: {panel_qty}'
        )

        return {
            'monthly_consumption_mwh': monthly_mwh,
            'real_dc': f'{real_dc:.2f}',
            'real_ac': f'{real_ac:.2f}',
            'panel_qty': panel_qty,
            **_build_inverter_payload(inv_result),
        }

    def _calc_power(self, module_power_kw):
        """power mode: planned DC → inverters → panels."""
        planned_dc = self.planned_dc_power
        if planned_dc <= 0:
            raise UserError('Вкажіть планову потужність DC (кВт).')

        target_ac = _round_to_50(planned_dc / DC_AC_RATIO)
        target_ac = max(target_ac, MIN_AC_KW)

        inv_result = _select_inverters(target_ac)
        if not inv_result:
            raise UserError('Не вдалося підібрати інвертори.')

        real_ac = inv_result['total_ac']
        real_dc = real_ac * DC_AC_RATIO
        panel_qty = math.ceil(real_dc / module_power_kw) if module_power_kw else 0

        ratio = real_dc / real_ac
        if not (MIN_RATIO <= ratio <= MAX_RATIO):
            raise UserError(f'DC/AC коефіцієнт {ratio:.2f} виходить за межі {MIN_RATIO}–{MAX_RATIO}.')

        self.calc_info = (
            f'Режим: планова потужність | DC вхід: {planned_dc} кВт\n'
            f'Реальна AC: {real_ac} кВт | DC: {round(real_dc, 2)} кВт | Панелей: {panel_qty}'
        )

        return {
            'planned_dc_power': planned_dc,
            'real_dc': f'{real_dc:.2f}',
            'real_ac': f'{real_ac:.2f}',
            'panel_qty': panel_qty,
            **_build_inverter_payload(inv_result),
        }

    def _calc_roof(self, module_power_kw):
        """roof mode: area × coeff → DC → inverters → panels."""
        area = self.roof_area
        if area <= 0:
            raise UserError('Вкажіть площу даху (М²).')

        coeff = ROOF_COEFF_FLAT if self.roof_mount_type == 'flat' else ROOF_COEFF_TILTED
        dc_w = area * coeff
        dc_kw = dc_w / 1000.0

        target_ac = _round_to_50(dc_kw / DC_AC_RATIO)
        target_ac = max(target_ac, MIN_AC_KW)

        inv_result = _select_inverters(target_ac)
        if not inv_result:
            raise UserError('Не вдалося підібрати інвертори.')

        real_ac = inv_result['total_ac']
        real_dc = real_ac * DC_AC_RATIO
        panel_qty = math.ceil(real_dc / module_power_kw) if module_power_kw else 0

        self.calc_info = (
            f'Режим: площа даху | Площа: {area} М² | Коефіцієнт: {coeff} Вт/М²\n'
            f'DC: {round(dc_kw, 2)} кВт | AC: {real_ac} кВт | Панелей: {panel_qty}'
        )

        return {
            'roof_area': area,
            'roof_mount_type': self.roof_mount_type,
            'real_dc': f'{real_dc:.2f}',
            'real_ac': f'{real_ac:.2f}',
            'panel_qty': panel_qty,
            **_build_inverter_payload(inv_result),
        }

    def _calc_manual(self):
        """manual mode: user-selected inverters + panel qty."""
        inv_power_map = {i['name']: i['power'] for i in INVERTERS}

        def inv_power(model, qty):
            return inv_power_map.get(model, 0) * qty if model else 0

        real_ac = (
            inv_power(self.inverter_1_model, self.inverter_1_qty) +
            inv_power(self.inverter_2_model, self.inverter_2_qty) +
            inv_power(self.inverter_3_model, self.inverter_3_qty)
        )

        if real_ac < 30:
            raise UserError('Загальна AC потужність інверторів має бути не менше 30 кВт.')

        module_power_kw = int(self.module_type or 0) / 1000.0 if self.module_type else 0
        real_dc = (self.panel_qty_manual * module_power_kw) if module_power_kw else 0

        if real_ac > 0 and real_dc > 0:
            ratio = real_dc / real_ac
            if not (MIN_RATIO <= ratio <= MAX_RATIO):
                raise UserError(
                    f'DC/AC коефіцієнт {ratio:.2f} виходить за норму ({MIN_RATIO}–{MAX_RATIO}).'
                )

        self.calc_info = (
            f'Режим: вручну | AC: {real_ac} кВт | DC: {round(real_dc, 2)} кВт\n'
            f'Панелей: {self.panel_qty_manual}'
        )

        return {
            'real_dc': f'{real_dc:.2f}',
            'real_ac': f'{real_ac:.2f}',
            'panel_qty': self.panel_qty_manual,
            'inverter_1_model': self.inverter_1_model or '',
            'inverter_1_qty':   self.inverter_1_qty,
            'inverter_2_model': self.inverter_2_model or '',
            'inverter_2_qty':   self.inverter_2_qty,
            'inverter_3_model': self.inverter_3_model or '',
            'inverter_3_qty':   self.inverter_3_qty,
        }

    # ── UZE payload ───────────────────────────────────────────────────────────

    def _build_uze_payload(self):
        uze_qty = self.uze_qty
        max_qty = UZE_MODEL_LIMITS.get(self.uze_model)
        if max_qty and uze_qty > max_qty:
            raise UserError(
                f'Для моделі "{self.uze_model}" максимально допустима кількість: {max_qty}.'
            )

        return {
            'project_name':   self.project_name,
            'manager':        self.manager,
            'region':         self.region,
            'uze_model':      self.uze_model or '',
            'uze_qty':        uze_qty,
            'uze_vat':        self.uze_vat or '',
            'equipment_vat':  self.equipment_vat or '',
            'currency':       self.currency_kp,
            'usage_type':     self.usage_type or '',
            'delivery_term':  self.delivery_term or '',
            'payment_terms':  self.payment_terms_kp or '',
            'delivery_terms': self.delivery_terms or '',
        }

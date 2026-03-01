"""
Фаза 3: Імпорт 4,171 нагод (deals) з Pipedrive в Odoo як crm.lead.

Запуск на сервері:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/import_deals_phase3.py
"""
import pandas as pd
import re
from datetime import datetime

XLSX_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/deals.xlsx'

# --- Маппінг власників Pipedrive → частина прізвища (для пошуку в Odoo) ---
OWNER_MAP = {
    'Наталія Гадайчук':     'Гадайчук',
    'Юрій Ходаківський':    'Ходаківський',
    'Андрій Селезньов':     'Селезньов',
    'Станіслав Бобровицький': 'Бобровицький',
    'Ігор Бєлік':           None,   # вже не в компанії → admin
    'Сергій Толочко':       'Толочко',
    'Максим Сидоров':       'Сидоров',
    'Богдан Безверхий':     None,
    'Олександр Достовалов': 'Достовалов',
    'Віталій Стоцький':     'Стоцький',
    'Микола Тубіш':         'Тубіш',
    'Юрій Лисенко':         'Лисенко',
    'Яна Курнаєва':         'Курнаєва',
    'Леся':                 'Радіоненко',
    'Павлов Дмитро':        'Павлов',
    'Олександр Коростіль':  'Коростіль',
    'Ксенія Коваленко':     None,
    'Дмитро Петров':        'Петров',
    'Ірина Бакуменко':      'Бакуменко',
    'Олександр Пилипенко':  None,
    'Ольга Вергун':         None,
    'Ольга':                None,   # неоднозначно → admin
}

FINANCING_MAP = {
    'Власні':                   'own',
    'Кредитні':                 'credit',
    'Власні (аванс)/Кредитні':  'mixed',
}

PROJECT_TYPE_MAP = {
    'СЕС':     'ses',
    'УЗЕ':     'uze',
    'СЕС+УЗЕ': 'ses_uze',
}

def clean_str(v):
    if pd.isna(v):
        return False
    s = str(v).strip()
    return s if s else False

def clean_float(v):
    if pd.isna(v):
        return False
    try:
        return float(v)
    except (ValueError, TypeError):
        return False

def clean_date(v):
    if pd.isna(v):
        return False
    try:
        if isinstance(v, str):
            return v[:10]
        return v.strftime('%Y-%m-%d')
    except Exception:
        return False

print('=== Фаза 3: Імпорт нагод (Deals) ===')
print('Читаємо xlsx...')
df = pd.read_excel(XLSX_PATH)
print(f'Завантажено {len(df)} нагод')

# --- Будуємо довідники ---

# 1. pipedrive org_id → odoo partner_id
print('Завантажуємо довідники...')
imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'),
     ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
org_to_odoo = {int(r['name'].replace('pipedrive_org_', '')): r['res_id'] for r in imd}

# 2. pipedrive person_id → odoo partner_id
person_partners = env['res.partner'].search_read(
    [('pipedrive_person_id', '>', 0)],
    ['pipedrive_person_id', 'id']
)
person_to_odoo = {r['pipedrive_person_id']: r['id'] for r in person_partners}

# 3. Вже імпортовані deals
existing_deals = set(
    env['crm.lead'].search([('pipedrive_deal_id', '>', 0)]).mapped('pipedrive_deal_id')
)
print(f'  {len(existing_deals)} вже імпортованих нагод')

# 4. Users — будуємо за прізвищем
all_users = env['res.users'].search_read(
    [('active', '=', True)], ['name', 'id']
)
surname_to_uid = {}
for u in all_users:
    parts = u['name'].split()
    for part in parts:
        surname_to_uid[part] = u['id']
admin_uid = env.ref('base.user_admin').id

def find_user(owner_str):
    if not owner_str or pd.isna(owner_str):
        return admin_uid
    # Беремо перше слово до "/" як прізвище або ім'я
    owner_clean = str(owner_str).split('/')[0].strip()
    # Шукаємо в OWNER_MAP
    for key, surname in OWNER_MAP.items():
        if key.lower() in owner_clean.lower():
            if surname:
                return surname_to_uid.get(surname, admin_uid)
            return admin_uid
    # Спробуємо по прізвищу напряму
    first_word = owner_clean.split()[0] if owner_clean else ''
    return surname_to_uid.get(first_word, admin_uid)

# 5. Teams
kc_team = env['crm.team'].search([('name', 'ilike', 'Колл')], limit=1)
sales_team = env['crm.team'].search([('name', 'ilike', 'Sales')], limit=1)
credit_team = env['crm.team'].search([('name', 'ilike', 'кредит')], limit=1)

print(f'  КЦ team: {kc_team.name if kc_team else "NOT FOUND"}')
print(f'  Sales team: {sales_team.name if sales_team else "NOT FOUND"}')
print(f'  Credit team: {credit_team.name if credit_team else "NOT FOUND"}')

def get_team(pipeline):
    if not pipeline:
        return kc_team
    p = str(pipeline)
    if 'Менеджер' in p:
        return sales_team
    if 'кредит' in p.lower():
        return credit_team
    return kc_team  # "Ліди" та "Воронка Оператор"

# 6. Stages — завантажуємо і будуємо маппінг по uk_UA назві
all_stages = env['crm.stage'].search_read([], ['name', 'team_id', 'sequence'])
stage_by_name = {}
for s in all_stages:
    name = s['name']
    if isinstance(name, dict):
        uk_name = name.get('uk_UA') or name.get('en_US') or ''
    else:
        uk_name = str(name)
    stage_by_name[uk_name.strip()] = s['id']

print(f'  Знайдено {len(stage_by_name)} stages: {list(stage_by_name.keys())}')

def get_or_create_stage(stage_name, team):
    """Знаходимо або створюємо stage."""
    if not stage_name:
        return False
    # Точний збіг
    if stage_name in stage_by_name:
        return stage_by_name[stage_name]
    # Частковий збіг
    for k, sid in stage_by_name.items():
        if stage_name.lower() in k.lower() or k.lower() in stage_name.lower():
            return sid
    # Не знайдено — створюємо
    new_stage = env['crm.stage'].create({
        'name': stage_name,
        'team_id': team.id if team else False,
        'sequence': 10,
    })
    stage_by_name[stage_name] = new_stage.id
    print(f'  Створено stage: {stage_name}')
    return new_stage.id

# --- Основний цикл ---
created = 0
won_count = 0
lost_count = 0
skipped = 0
errors = 0

for _, row in df.iterrows():
    pd_deal_id = int(row['Ідентифікатор'])

    if pd_deal_id in existing_deals:
        skipped += 1
        continue

    # Компанія і контакт
    pd_org_id = row.get('Ідентифікатор організації')
    pd_person_id = row.get('Ідентифікатор контактної особи')

    partner_id = False
    if not pd.isna(pd_org_id):
        partner_id = org_to_odoo.get(int(pd_org_id), False)

    contact_id = False
    if not pd.isna(pd_person_id):
        contact_id = person_to_odoo.get(int(pd_person_id), False)

    # Якщо нема компанії але є контакт — беремо компанію контакта
    if not partner_id and contact_id:
        person = env['res.partner'].browse(contact_id)
        if person.parent_id:
            partner_id = person.parent_id.id

    # Team і stage
    pipeline = clean_str(row.get('Воронка продажів'))
    team = get_team(pipeline)
    stage_name = clean_str(row.get('Етап'))
    stage_id = get_or_create_stage(stage_name, team) if stage_name else False

    # Власник
    user_id = find_user(row.get('Власник'))

    # Стан
    state = clean_str(row.get('Стан'))
    is_won = state == 'Виграно'
    is_lost = state == 'Програно'
    active = not (is_won or is_lost)

    vals = {
        'name': clean_str(row.get('Заголовок')) or (
            env['res.partner'].browse(partner_id).name if partner_id else 'Нагода'
        ),
        'partner_id': partner_id or False,
        'user_id': user_id,
        'team_id': team.id if team else False,
        'stage_id': stage_id or False,
        'active': active,
        'pipedrive_deal_id': pd_deal_id,
        'type': 'opportunity',
    }

    # Кастомні поля
    financing = clean_str(row.get('Тип фінансування'))
    if financing:
        vals['financing_type'] = FINANCING_MAP.get(financing, False)

    is_bank = row.get('Банківський клієнт')
    if not pd.isna(is_bank) and str(is_bank).strip().lower() in ('1', 'true', 'так', 'yes'):
        vals['is_bank_client'] = True

    for pipedrive_col, odoo_field in [
        ('Потужність СЕС, кВт', 'power_ses_kw'),
        ('Ємність УЗЕ, кВт*год', 'capacity_uze_kwh'),
    ]:
        v = clean_float(row.get(pipedrive_col))
        if v:
            vals[odoo_field] = v

    for pipedrive_col, odoo_field in [
        ('Дата виконання первинних розрахунків', 'primary_calc_date'),
        ('Фактична дата замірів', 'measurement_date'),
        ('Планова дата надходження авансу', 'advance_planned_date'),
        ('Фактична дата отримання авансу', 'advance_actual_date'),
        ('Очікувана дата закриття', 'date_deadline'),
    ]:
        v = clean_date(row.get(pipedrive_col))
        if v:
            vals[odoo_field] = v

    loss_reason = clean_str(row.get('Причина програшу'))
    if loss_reason:
        vals['loss_reason_text'] = loss_reason

    try:
        lead = env['crm.lead'].create(vals)

        # Won/Lost статус
        if is_won:
            lead.action_set_won()
            won_count += 1
        elif is_lost:
            lead.write({'active': False, 'probability': 0})
            lost_count += 1

        created += 1
        existing_deals.add(pd_deal_id)

    except Exception as e:
        errors += 1
        if errors <= 10:
            print(f'  ПОМИЛКА (deal {pd_deal_id}): {e}')

    if created % 200 == 0 and created > 0:
        env.cr.commit()
        print(f'  Прогрес: {created+skipped}/{len(df)} (створено: {created})')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Створено:    {created} (won: {won_count}, lost: {lost_count})')
print(f'Пропущено:   {skipped}')
print(f'Помилки:     {errors}')

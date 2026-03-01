"""
Виправляє пропущені поля нагод (crm.lead):
  1. project_type (Мітка в deals.xlsx: СЕС/УЗЕ/СЕС+УЗЕ)
  2. credit_specialist_id — зберігаємо як stored поле (потрібна міграція моделі)
     → поки просто логуємо що є в даних

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/fix_deal_fields.py
"""
import pandas as pd

XLSX_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/deals.xlsx'

PROJECT_TYPE_MAP = {
    'СЕС':       'ses',
    'УЗЕ':       'uze',
    'СЕС + УЗЕ': 'ses_uze',
    'УЗЕ, СЕС':  'ses_uze',
    'СЕС+УЗЕ':   'ses_uze',
}

# Кредитні спеціалісти — прізвище для пошуку в Odoo
CREDIT_SPECIALIST_MAP = {
    'Оксана Коваленко':    'Сущенко',   # Сущенко Оксана Миколаївна в Odoo
    'Яна Курнаєва':        'Курнаєва',
    'Леся Радіоненко':     'Радіоненко',
    'Олександр Коростіль': 'Коростіль',
}

print('=== Виправлення полів нагод ===')
df = pd.read_excel(XLSX_PATH)
print(f'  {len(df)} рядків в deals.xlsx')

# Будуємо маппінг pipedrive_deal_id → odoo lead_id
leads = env['crm.lead'].search_read(
    [('pipedrive_deal_id', '>', 0)],
    ['pipedrive_deal_id', 'id', 'project_type']
)
deal_map = {r['pipedrive_deal_id']: r for r in leads}
print(f'  {len(deal_map)} нагод з pipedrive_deal_id в Odoo')

# Users по прізвищу
all_users = env['res.users'].search_read([('active', '=', True)], ['name', 'id'])
surname_to_uid = {}
for u in all_users:
    parts = u['name'].split()
    for part in parts:
        if len(part) > 2:
            surname_to_uid[part.lower()] = u['id']

def find_user(name_str):
    if not name_str:
        return False
    for key, surname in CREDIT_SPECIALIST_MAP.items():
        if key.lower() in name_str.lower():
            return surname_to_uid.get(surname.lower(), False)
    return False

# --- project_type ---
print('\n--- project_type ---')
updated_type = 0
already_set = 0

for _, row in df.iterrows():
    pd_deal_id = int(row['Ідентифікатор'])
    lead_rec = deal_map.get(pd_deal_id)
    if not lead_rec:
        continue

    raw_label = row.get('Мітка')
    if pd.isna(raw_label) or not str(raw_label).strip():
        continue

    label = str(raw_label).strip()
    ptype = PROJECT_TYPE_MAP.get(label)
    if not ptype:
        print(f'  ! Невідома мітка: {label}')
        continue

    if lead_rec['project_type'] == ptype:
        already_set += 1
        continue

    env['crm.lead'].browse(lead_rec['id']).write({'project_type': ptype})
    updated_type += 1

env.cr.commit()
print(f'  Оновлено project_type: {updated_type}')
print(f'  Вже було встановлено: {already_set}')

# --- credit_specialist_id ---
print('\n--- credit_specialist_id ---')
updated_cs = 0
not_found = 0

for _, row in df.iterrows():
    pd_deal_id = int(row['Ідентифікатор'])
    lead_rec = deal_map.get(pd_deal_id)
    if not lead_rec:
        continue

    raw_cs = row.get('Кредитний спеціаліст')
    if pd.isna(raw_cs) or not str(raw_cs).strip():
        continue

    cs_name = str(raw_cs).strip()
    uid = find_user(cs_name)
    if not uid:
        not_found += 1
        if not_found <= 5:
            print(f'  ! Не знайдено спеціаліста: {cs_name}')
        continue

    env['crm.lead'].browse(lead_rec['id']).write({'credit_specialist_id': uid})
    updated_cs += 1

env.cr.commit()
print(f'  Оновлено credit_specialist_id: {updated_cs}')
print(f'  Не знайдено в Odoo: {not_found}')

print('\n=== Готово ===')

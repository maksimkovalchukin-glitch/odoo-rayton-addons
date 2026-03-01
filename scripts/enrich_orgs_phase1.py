"""
Фаза 1: Збагачення 38k компаній в Odoo даними з Pipedrive organizations export.

Запуск на сервері:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/enrich_orgs_phase1.py
"""
import pandas as pd
import re
import sys

XLSX_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/organizations.xlsx'

STATUS_MAP = {
    'Цільовий':                      'target',
    'Не цільовий':                   'non_target',
    'Не визначено':                  'undefined',
    'Прифронтовий':                  'frontline',
    'Без контактів':                 'no_contacts',
    'Реалізовано конкурентами':      'competitor',
    'Територіально на паузі':        'paused',
    'Не пройшов перевірку юр. відділом': 'legal_rejected',
}

TEMP_MAP = {
    'Cold lead':    'cold',
    'Warm lead':    'warm',
    'Hot lead':     'hot',
    'Customer':     'customer',
}

def clean_str(v):
    if pd.isna(v):
        return False
    s = str(v).strip()
    return s if s else False

def map_status(v):
    """Беремо перше значення якщо є комбо типу 'Цільовий, Прифронтовий'"""
    if pd.isna(v):
        return False
    first = str(v).split(',')[0].strip()
    return STATUS_MAP.get(first, False)

def map_temp(v):
    if pd.isna(v):
        return False
    first = str(v).split(',')[0].strip()
    return TEMP_MAP.get(first, False)

def clean_edrpou(v):
    if pd.isna(v):
        return False
    s = re.sub(r'[^\d]', '', str(int(v)) if isinstance(v, float) else str(v))
    return s if len(s) >= 6 else False

print('=== Фаза 1: Збагачення компаній ===')
print('Читаємо xlsx...')

df = pd.read_excel(XLSX_PATH)
print(f'Завантажено {len(df)} організацій')

# Завантажуємо всі external IDs за один запит
imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'),
     ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
# Будуємо словник: pipedrive_id -> odoo_partner_id
pd_to_odoo = {}
for rec in imd:
    try:
        pd_id = int(rec['name'].replace('pipedrive_org_', ''))
        pd_to_odoo[pd_id] = rec['res_id']
    except ValueError:
        pass

print(f'Знайдено {len(pd_to_odoo)} external IDs в Odoo')

updated = 0
skipped = 0
no_match = 0

for _, row in df.iterrows():
    pd_id = int(row['Ідентифікатор'])
    partner_id = pd_to_odoo.get(pd_id)

    if not partner_id:
        no_match += 1
        continue

    partner = env['res.partner'].browse(partner_id)
    if not partner.exists():
        no_match += 1
        continue

    vals = {}

    edrpou = clean_edrpou(row.get('ЄДРПОУ'))
    if edrpou and not partner.vat:
        vals['vat'] = edrpou

    kved = clean_str(row.get('Назва кведу ЄДРПОУ'))
    if kved and not partner.kved_name:
        vals['kved_name'] = kved

    status = map_status(row.get('Статус Клієнта'))
    if status and not partner.client_status:
        vals['client_status'] = status

    temp = map_temp(row.get('Мітка'))
    if temp and not partner.lead_temp:
        vals['lead_temp'] = temp

    source = clean_str(row.get('Джерело'))
    if source and not partner.partner_source:
        vals['partner_source'] = source

    director = clean_str(row.get('Керівник'))
    if director and not partner.director_name:
        vals['director_name'] = director

    link = clean_str(row.get('Посилання з ресурсу'))
    if link and not partner.resource_link:
        vals['resource_link'] = link

    consumption = row.get('Споживання, мВт*год/міс')
    if not pd.isna(consumption):
        try:
            c = float(str(consumption).split('/')[0].split(' ')[0].replace(',', '.'))
            if c > 0 and not partner.consumption_mwh:
                vals['consumption_mwh'] = c
        except (ValueError, TypeError):
            pass

    uze = row.get('Пропозиція УЗЕ')
    if not pd.isna(uze) and str(uze).strip().lower() in ('1', 'true', 'так', 'yes'):
        vals['uze_proposal'] = True

    if vals:
        partner.write(vals)
        updated += 1
    else:
        skipped += 1

    if (updated + skipped) % 1000 == 0:
        env.cr.commit()
        print(f'  Прогрес: {updated+skipped}/{len(df)} (оновлено: {updated})')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Оновлено:    {updated}')
print(f'Без змін:    {skipped}')
print(f'Не знайдено: {no_match}')

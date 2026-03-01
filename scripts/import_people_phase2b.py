"""
Фаза 2b: Імпорт пропущених контактів які мали активності в Pipedrive.
Ці контакти були пропущені в фазі 2 бо не мали мобільного телефону та email,
але вони важливі — до них були прив'язані дзвінки/завдання/нотатки.

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/import_people_phase2b.py
"""
import pandas as pd
import re

PEOPLE_PATH     = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/people.xlsx'
ACTIVITIES_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/activities.xlsx'

MOBILE_OPS = {'50','63','66','67','68','73','91','93','95','96','97','98','99'}

PHONE_TYPE_MAP = {
    'Телефон - Мобільний': 'mobile',
    'Телефон - Робочий':   'work',
    'Телефон - Домашній':  'home',
    'Телефон - Інший':     'other',
}
EMAIL_COLS = [
    'Електронна пошта - Робочий',
    'Електронна пошта - Домашній',
    'Електронна пошта - Інший',
]

def normalize_phone(p):
    d = re.sub(r'[^0-9]', '', str(p))
    if len(d) == 10 and d.startswith('0'):
        d = '380' + d[1:]
    if d.startswith('380') and len(d) == 12:
        return d
    return None

def is_mobile(norm):
    return norm and norm[3:5] in MOBILE_OPS

def clean_str(v):
    if pd.isna(v):
        return ''
    return str(v).strip()

print('=== Фаза 2b: Контакти з активностями ===')

# 1. Збираємо person_ids що мають активності
print('Читаємо activities.xlsx...')
acts = pd.read_excel(ACTIVITIES_PATH)
person_ids_with_activities = set(
    int(v) for v in acts['Ідентифікатор контактної особи'].dropna()
)
print(f'  Унікальних контактів з активностями: {len(person_ids_with_activities)}')

# 2. Вже імпортовані
existing_ids = set(
    env['res.partner'].search([('pipedrive_person_id', '>', 0)]).mapped('pipedrive_person_id')
)
print(f'  Вже імпортовано: {len(existing_ids)}')

# 3. org_id → odoo partner_id
imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'),
     ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
org_to_odoo = {int(r['name'].replace('pipedrive_org_', '')): r['res_id'] for r in imd}

# 4. Існуючі телефони
existing_phones = {}
for ph in env['res.partner.phone'].search_read([], ['phone', 'partner_id']):
    existing_phones.setdefault(ph['phone'], set()).add(ph['partner_id'][0])

# 5. Читаємо people і фільтруємо потрібних
print('Читаємо people.xlsx...')
df = pd.read_excel(PEOPLE_PATH)

created = 0
skipped_existing = 0
skipped_no_name = 0
errors = 0

for _, row in df.iterrows():
    pd_id = int(row['Ідентифікатор'])

    # Тільки ті що мають активності
    if pd_id not in person_ids_with_activities:
        continue

    # Вже імпортовані — пропускаємо
    if pd_id in existing_ids:
        skipped_existing += 1
        continue

    name = clean_str(row.get("Ім'я/Назва")) or clean_str(row.get("Ім'я"))
    if not name:
        skipped_no_name += 1
        continue

    # Збираємо всі телефони (мобільні + стаціонарні)
    all_phones = []
    for col, ptype in PHONE_TYPE_MAP.items():
        raw = row.get(col)
        if not pd.isna(raw):
            norm = normalize_phone(raw)
            if norm:
                # мобільний має пріоритет як primary
                is_prim = is_mobile(norm) and not any(
                    is_mobile(p['phone']) for p in all_phones
                )
                all_phones.append({
                    'phone': norm,
                    'phone_type': ptype,
                    'is_primary': False,
                })

    # Якщо нема мобільного — перший стає primary
    if all_phones and not any(is_mobile(p['phone']) for p in all_phones):
        all_phones[0]['is_primary'] = True
    elif all_phones:
        for p in all_phones:
            if is_mobile(p['phone']):
                p['is_primary'] = True
                break

    # Email
    email = ''
    for ecol in EMAIL_COLS:
        e = clean_str(row.get(ecol))
        if e and '@' in e:
            email = e
            break

    # Компанія
    pd_org_id = row.get('Ідентифікатор організації')
    parent_id = False
    if not pd.isna(pd_org_id):
        parent_id = org_to_odoo.get(int(pd_org_id), False)

    vals = {
        'name': name,
        'company_type': 'person',
        'parent_id': parent_id,
        'function': clean_str(row.get('Посада')) or False,
        'email': email or False,
        'comment': clean_str(row.get('Примітка')) or False,
        'pipedrive_person_id': pd_id,
    }

    try:
        partner = env['res.partner'].create(vals)

        for ph in all_phones:
            ph['partner_id'] = partner.id
            env['res.partner.phone'].create(ph)
            existing_phones.setdefault(ph['phone'], set()).add(partner.id)

        created += 1
        existing_ids.add(pd_id)

    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f'  ПОМИЛКА ({name}): {e}')

    if created % 500 == 0 and created > 0:
        env.cr.commit()
        print(f'  Прогрес: створено {created}')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Створено:        {created}')
print(f'Вже існували:    {skipped_existing}')
print(f'Без імені:       {skipped_no_name}')
print(f'Помилки:         {errors}')

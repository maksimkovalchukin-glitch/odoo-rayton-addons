"""
Фаза 2: Імпорт 123k контактів (People) з Pipedrive в Odoo як res.partner.

Запуск на сервері:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/import_people_phase2.py
"""
import pandas as pd
import re

XLSX_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/people.xlsx'

MOBILE_OPS = {'50','63','66','67','68','73','91','93','95','96','97','98','99'}

PHONE_TYPE_MAP = {
    'Телефон - Мобільний': 'mobile',
    'Телефон - Робочий':   'work',
    'Телефон - Домашній':  'home',
    'Телефон - Інший':     'other',
}

def normalize_phone(p):
    """Нормалізуємо до 380XXXXXXXXX (12 цифр). Повертає None якщо невалідний."""
    d = re.sub(r'[^0-9]', '', str(p))
    if len(d) == 10 and d.startswith('0'):
        d = '380' + d[1:]
    if d.startswith('380') and len(d) == 12:
        return d
    return None

def is_mobile(normalized):
    if not normalized:
        return False
    return normalized[3:5] in MOBILE_OPS

def clean_str(v):
    if pd.isna(v):
        return ''
    return str(v).strip()

print('=== Фаза 2: Імпорт контактів (People) ===')
print('Читаємо xlsx...')

df = pd.read_excel(XLSX_PATH)
print(f'Завантажено {len(df)} контактів')

# --- Будуємо словники для швидкого пошуку ---

# 1. pipedrive org_id → odoo partner_id
print('Завантажуємо external IDs...')
imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'),
     ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
org_to_odoo = {}
for rec in imd:
    try:
        pd_org_id = int(rec['name'].replace('pipedrive_org_', ''))
        org_to_odoo[pd_org_id] = rec['res_id']
    except ValueError:
        pass
print(f'  {len(org_to_odoo)} org external IDs')

# 2. Вже імпортовані pipedrive_person_id → skip
existing_person_ids = set(
    env['res.partner'].search([('pipedrive_person_id', '>', 0)]).mapped('pipedrive_person_id')
)
print(f'  {len(existing_person_ids)} вже імпортованих контактів')

# 3. Існуючі телефони в res.partner.phone (phone → set of partner_ids)
print('Завантажуємо існуючі телефони...')
existing_phones = {}
for ph in env['res.partner.phone'].search_read([], ['phone', 'partner_id']):
    existing_phones.setdefault(ph['phone'], set()).add(ph['partner_id'][0])
print(f'  {len(existing_phones)} унікальних телефонів в системі')

# --- Основний цикл ---
created = 0
skipped_existing = 0
skipped_no_info = 0
merged_phone = 0
errors = 0

BATCH = 500
batch_count = 0

for _, row in df.iterrows():
    pd_person_id = int(row['Ідентифікатор'])

    # Пропускаємо вже імпортовані
    if pd_person_id in existing_person_ids:
        skipped_existing += 1
        continue

    name = clean_str(row.get("Ім'я/Назва")) or clean_str(row.get("Ім'я"))
    if not name:
        skipped_no_info += 1
        continue

    # Збираємо всі телефони
    all_phones = []
    for col, ptype in PHONE_TYPE_MAP.items():
        raw = row.get(col)
        if not pd.isna(raw):
            norm = normalize_phone(raw)
            if norm and is_mobile(norm):
                all_phones.append({'phone': norm, 'phone_type': ptype, 'is_primary': False})

    if all_phones:
        all_phones[0]['is_primary'] = True

    # Email
    email = ''
    for ecol in ['Електронна пошта - Робочий', 'Електронна пошта - Домашній', 'Електронна пошта - Інший']:
        e = clean_str(row.get(ecol))
        if e and '@' in e:
            email = e
            break

    # Без телефону і email → skip
    if not all_phones and not email:
        skipped_no_info += 1
        continue

    # Пошук батьківської компанії
    pd_org_id = row.get('Ідентифікатор організації')
    parent_id = False
    if not pd.isna(pd_org_id):
        parent_id = org_to_odoo.get(int(pd_org_id), False)

    # Перевірка дублю по телефону в межах компанії
    if all_phones and parent_id:
        first_phone = all_phones[0]['phone']
        if first_phone in existing_phones:
            phone_partners = existing_phones[first_phone]
            # Якщо телефон вже є у контакта цієї компанії → skip (merge)
            siblings = env['res.partner'].browse(list(phone_partners)).filtered(
                lambda p: p.parent_id.id == parent_id
            )
            if siblings:
                merged_phone += 1
                continue

    # Створюємо контакт
    vals = {
        'name': name,
        'company_type': 'person',
        'parent_id': parent_id,
        'function': clean_str(row.get('Посада')) or False,
        'email': email or False,
        'comment': clean_str(row.get('Примітка')) or False,
        'pipedrive_person_id': pd_person_id,
    }

    try:
        partner = env['res.partner'].create(vals)

        # Телефони
        for ph in all_phones:
            ph['partner_id'] = partner.id
            env['res.partner.phone'].create(ph)
            existing_phones.setdefault(ph['phone'], set()).add(partner.id)

        created += 1
        existing_person_ids.add(pd_person_id)

    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f'  ПОМИЛКА ({name}): {e}')

    batch_count += 1
    if batch_count % BATCH == 0:
        env.cr.commit()
        total = created + skipped_existing + skipped_no_info + merged_phone + errors
        print(f'  Прогрес: {total}/{len(df)} (створено: {created}, пропущено: {skipped_existing+skipped_no_info+merged_phone})')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Створено:           {created}')
print(f'Вже існували:       {skipped_existing}')
print(f'Без контактних:     {skipped_no_info}')
print(f'Дублі по телефону:  {merged_phone}')
print(f'Помилки:            {errors}')

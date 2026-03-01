"""
Виправляє телефони контактів, які не потрапили через баг:
  - Два телефони через кому в одній клітинці → normalize_phone давала None
  - Не-мобільні номери також скіпалися

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/fix_phones.py
"""
import pandas as pd
import re

XLSX_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/people.xlsx'

PHONE_TYPE_MAP = {
    'Телефон - Мобільний': 'mobile',
    'Телефон - Робочий':   'work',
    'Телефон - Домашній':  'home',
    'Телефон - Інший':     'other',
}

MOBILE_OPS = {'50','63','66','67','68','73','91','93','95','96','97','98','99'}


def normalize_phone(p):
    """Нормалізуємо до 380XXXXXXXXX (12 цифр). Повертає None якщо невалідний."""
    d = re.sub(r'[^0-9]', '', str(p).strip())
    if len(d) == 10 and d.startswith('0'):
        d = '380' + d[1:]
    if d.startswith('380') and len(d) == 12:
        return d
    return None


def extract_phones_from_cell(raw, ptype):
    """Розбиває клітинку на кілька телефонів (через кому або пробіл)."""
    if pd.isna(raw):
        return []
    result = []
    # Розбиваємо по комі або пробілу
    parts = re.split(r'[,;\s]+', str(raw).strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        norm = normalize_phone(part)
        if norm:
            result.append({'phone': norm, 'phone_type': ptype})
    return result


print('=== Виправлення телефонів ===')

df = pd.read_excel(XLSX_PATH)
print(f'  {len(df)} контактів в people.xlsx')

all_ph_records = env['res.partner.phone'].search_read([], ['phone', 'partner_id'])
existing_by_partner = {}  # partner_id → set of phones
for r in all_ph_records:
    pid = r['partner_id'][0]
    existing_by_partner.setdefault(pid, set()).add(r['phone'])

# Знаходимо всі контакти з pipedrive_person_id
person_map = {r['pipedrive_person_id']: r['id']
              for r in env['res.partner'].search_read(
                  [('pipedrive_person_id', '>', 0)],
                  ['pipedrive_person_id', 'id']
              )}
print(f'  {len(person_map)} контактів з pipedrive_person_id в Odoo')

added = 0
errors = 0

for _, row in df.iterrows():
    pd_pid = int(row['Ідентифікатор'])
    odoo_pid = person_map.get(pd_pid)
    if not odoo_pid:
        continue

    # Збираємо всі телефони з усіх колонок
    all_phones = []
    for col, ptype in PHONE_TYPE_MAP.items():
        raw = row.get(col)
        phones = extract_phones_from_cell(raw, ptype)
        all_phones.extend(phones)

    if not all_phones:
        continue

    # Поточні телефони цього контакта
    current = existing_by_partner.get(odoo_pid, set())

    # Встановлюємо primary для першого нового (якщо ще немає жодного)
    has_primary = bool(current)
    new_added = 0

    for ph in all_phones:
        if ph['phone'] in current:
            continue
        is_primary = not has_primary and new_added == 0
        try:
            env['res.partner.phone'].create({
                'partner_id': odoo_pid,
                'phone': ph['phone'],
                'phone_type': ph['phone_type'],
                'is_primary': is_primary,
                'sequence': 10 + new_added,
            })
            current.add(ph['phone'])
            existing_by_partner[odoo_pid] = current
            new_added += 1
            added += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f'  ! pid={odoo_pid} {ph["phone"]}: {e}')

    if added % 1000 == 0 and added > 0:
        env.cr.commit()
        print(f'  Прогрес: {added} доданих телефонів...')

env.cr.commit()
print(f'\nДодано нових телефонів: {added}')
print(f'Помилок: {errors}')
print('=== Готово ===')

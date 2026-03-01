"""
Імпорт черги менеджерів з Excel → rayton.manager.queue.

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/import_manager_queue.py
"""
import pandas as pd

XLSX_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/leads_queue.xlsx'

print('=== Імпорт черги менеджерів ===')

df = pd.read_excel(XLSX_PATH)
print(f'  {len(df)} рядків')

# Колонки Excel → queue_type
QUEUE_COL_MAP = {
    'Черга заявки колл-центр':    'kcc',
    'Черга \nвхідні заявки':       'incoming',
    'Черга \nвідділ кредитування': 'credit',
}

# Прізвище → user_id в Odoo
all_users = env['res.users'].search_read([('active', '=', True), ('share', '=', False)], ['name', 'id'])
surname_to_uid = {}
for u in all_users:
    parts = u['name'].split()
    if parts:
        surname_to_uid[parts[0].lower()] = u['id']
    # Також по повному імені
    surname_to_uid[u['name'].lower()] = u['id']

def find_user(name):
    clean = str(name).strip().lower()
    if clean in surname_to_uid:
        return surname_to_uid[clean]
    # Спробуємо по першому слову (прізвище)
    parts = clean.split()
    if parts:
        return surname_to_uid.get(parts[0])
    return None

# Очищаємо старі записи
env['rayton.manager.queue'].search([]).unlink()
env.cr.commit()
print('  Старі записи видалено')

created = 0
errors = 0
for _, row in df.iterrows():
    manager_name = str(row.get('Менеджер', '') or '').strip()
    if not manager_name:
        continue

    uid = find_user(manager_name)
    if not uid:
        print(f'  ! Не знайдено user: {manager_name}')
        errors += 1
        continue

    seq = 10
    for col, qtype in QUEUE_COL_MAP.items():
        in_queue = row.get(col)
        if in_queue is True or str(in_queue).strip().lower() in ('true', '1', 'yes', 'так'):
            try:
                env['rayton.manager.queue'].create({
                    'user_id': uid,
                    'queue_type': qtype,
                    'sequence': seq,
                    'is_paused': False,
                })
                created += 1
            except Exception as e:
                print(f'  ! {manager_name} / {qtype}: {e}')
                errors += 1
        seq += 1

env.cr.commit()
print(f'\nСтворено: {created} записів у чергах')
print(f'Помилок:  {errors}')
print('\n=== Готово ===')

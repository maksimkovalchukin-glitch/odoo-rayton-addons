"""
Додає "Контакт: <ім'я>" до тіла існуючих activity-повідомлень в чаттері.

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/fix_activity_contact.py
"""
import pandas as pd
import re

ACTIVITIES_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/activities.xlsx'

print('=== Додавання контактної особи в активності ===')

df = pd.read_excel(ACTIVITIES_PATH)
print(f'  {len(df)} рядків в activities.xlsx')

df_contact = df[df['Контактна особа'].notna() & (df['Контактна особа'].astype(str).str.strip() != '')].copy()
print(f'  {len(df_contact)} рядків з контактною особою')

# act_id → message_id через ir_model_data
env.cr.execute("""
    SELECT name, res_id FROM ir_model_data
    WHERE module = '__import__'
      AND model = 'mail.message'
      AND name LIKE 'pipedrive_act_%'
""")
ext_map = {r[0]: r[1] for r in env.cr.fetchall()}
print(f'  {len(ext_map)} activity-повідомлень в Odoo')

# Читаємо поточні тіла одним запитом
msg_ids = list(ext_map.values())
env.cr.execute("SELECT id, body FROM mail_message WHERE id = ANY(%s)", [msg_ids])
body_map = {r[0]: r[1] for r in env.cr.fetchall()}

updated = 0
not_found = 0
already_has = 0

updates = []  # (new_body, msg_id)

for _, row in df_contact.iterrows():
    act_id = int(row['Ідентифікатор'])
    msg_id = ext_map.get('pipedrive_act_%d' % act_id)
    if not msg_id:
        not_found += 1
        continue

    body = body_map.get(msg_id, '') or ''
    if 'Контакт:' in body:
        already_has += 1
        continue

    # Прибираємо суфікс "(Контакт з бази ЯСНО)" та подібні
    contact_raw = str(row['Контактна особа']).strip()
    contact_name = re.sub(r'\s*\([^)]*\)\s*$', '', contact_raw).strip() or contact_raw

    # Вставляємо після першого </strong>...<br/>
    # Поточна структура: <strong>icon type</strong> status<br/>
    # Хочемо: <strong>icon type</strong> status<br/>Контакт: name<br/>
    marker = '</strong>'
    if marker in body:
        # Знаходимо перший <br/> після </strong>
        idx_strong = body.index(marker) + len(marker)
        idx_br = body.find('<br/>', idx_strong)
        if idx_br >= 0:
            insert_pos = idx_br + len('<br/>')
            new_body = body[:insert_pos] + ('Контакт: %s<br/>' % contact_name) + body[insert_pos:]
        else:
            # fallback: вставити перед </p>
            new_body = body.replace('</p>', 'Контакт: %s<br/></p>' % contact_name, 1)
    else:
        not_found += 1
        continue

    updates.append((new_body, msg_id))
    body_map[msg_id] = new_body  # оновлюємо кеш

    if len(updates) >= 2000:
        env.cr.executemany("UPDATE mail_message SET body=%s WHERE id=%s", updates)
        env.cr.commit()
        updated += len(updates)
        print(f'  Прогрес: {updated} оновлено...')
        updates = []

if updates:
    env.cr.executemany("UPDATE mail_message SET body=%s WHERE id=%s", updates)
    env.cr.commit()
    updated += len(updates)

print(f'\nОновлено: {updated}')
print(f'Вже мали "Контакт:": {already_has}')
print(f'Не знайдено в Odoo: {not_found}')
print('=== Готово ===')

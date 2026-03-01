"""
Фаза 4: Імпорт 51,932 нотаток з Pipedrive → mail.message (chatter) в Odoo.

Пріоритет прив'язки: угода > контакт > організація

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/import_notes_phase4.py
"""
import pandas as pd
from datetime import datetime

NOTES_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/notes.xlsx'

def clean_str(v):
    if pd.isna(v):
        return ''
    return str(v).strip()

print('=== Фаза 4: Імпорт нотаток ===')
print('Читаємо notes.xlsx...')
df = pd.read_excel(NOTES_PATH)
print(f'Завантажено {len(df)} нотаток')

# --- Довідники ---

# 1. pipedrive deal_id → crm.lead.id
deals = env['crm.lead'].search_read(
    [('pipedrive_deal_id', '>', 0)], ['pipedrive_deal_id', 'id']
)
deal_to_lead = {r['pipedrive_deal_id']: r['id'] for r in deals}
print(f'  {len(deal_to_lead)} угод в системі')

# 2. pipedrive person_id → res.partner.id
persons = env['res.partner'].search_read(
    [('pipedrive_person_id', '>', 0)], ['pipedrive_person_id', 'id']
)
person_to_partner = {r['pipedrive_person_id']: r['id'] for r in persons}
print(f'  {len(person_to_partner)} контактів в системі')

# 3. pipedrive org_id → res.partner.id (через ir.model.data)
imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'),
     ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
org_to_partner = {int(r['name'].replace('pipedrive_org_', '')): r['res_id'] for r in imd}
print(f'  {len(org_to_partner)} організацій в системі')

# 4. Користувачі за іменем → partner_id
all_users = env['res.users'].search_read([('active', '=', True)], ['name', 'partner_id'])
name_to_partner_id = {}
for u in all_users:
    name_to_partner_id[u['name'].lower()] = u['partner_id'][0]
    for part in u['name'].split():
        name_to_partner_id[part.lower()] = u['partner_id'][0]
admin_partner_id = env.ref('base.user_admin').partner_id.id

def find_author(username):
    if not username:
        return admin_partner_id
    u = str(username).strip().lower()
    if u in name_to_partner_id:
        return name_to_partner_id[u]
    for part in u.split():
        if part in name_to_partner_id:
            return name_to_partner_id[part]
    return admin_partner_id

# 5. Subtype для внутрішньої нотатки
mt_note = env.ref('mail.mt_note').id

# 6. Вже імпортовані (за pipedrive_note_id якщо є, або skip дублі по content+date)
# Зберігаємо в пам'яті set вже оброблених IDs через custom field або просто не перевіряємо
# (скрипт ідемпотентний — якщо запустити двічі, дублі нотаток з'являться)
# Тому перевіряємо через ir.model.data
existing_notes = set()
imd_notes = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'mail.message'),
     ('name', 'like', 'pipedrive_note_')],
    ['name']
)
for r in imd_notes:
    try:
        existing_notes.add(int(r['name'].replace('pipedrive_note_', '')))
    except ValueError:
        pass
print(f'  {len(existing_notes)} вже імпортованих нотаток')

# --- Основний цикл ---
created = 0
skipped_no_target = 0
skipped_existing = 0
errors = 0

for _, row in df.iterrows():
    note_id = int(row['Ідентифікатор'])

    if note_id in existing_notes:
        skipped_existing += 1
        continue

    content = clean_str(row.get('Вміст'))
    if not content:
        skipped_no_target += 1
        continue

    # Визначаємо куди прив'язати (пріоритет: угода > контакт > організація)
    res_model = False
    res_id = False

    pd_deal_id = row.get('Ідентифікатор угоди')
    pd_person_id = row.get('Ідентифікатор контактної особи')
    pd_org_id = row.get('Ідентифікатор організації')

    if not pd.isna(pd_deal_id):
        lead_id = deal_to_lead.get(int(pd_deal_id))
        if lead_id:
            res_model = 'crm.lead'
            res_id = lead_id

    if not res_id and not pd.isna(pd_person_id):
        partner_id = person_to_partner.get(int(pd_person_id))
        if partner_id:
            res_model = 'res.partner'
            res_id = partner_id

    if not res_id and not pd.isna(pd_org_id):
        partner_id = org_to_partner.get(int(pd_org_id))
        if partner_id:
            res_model = 'res.partner'
            res_id = partner_id

    if not res_id:
        skipped_no_target += 1
        continue

    # Дата
    date_raw = row.get('Час додавання')
    if pd.isna(date_raw):
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(date_raw, str):
        date_str = date_raw[:19]
    else:
        date_str = date_raw.strftime('%Y-%m-%d %H:%M:%S')

    author_pid = find_author(row.get('Користувач'))

    # Форматуємо body (HTML)
    body = f'<p>{content}</p>'

    try:
        msg = env['mail.message'].sudo().create({
            'res_id':       res_id,
            'model':        res_model,
            'body':         body,
            'date':         date_str,
            'author_id':    author_pid,
            'message_type': 'comment',
            'subtype_id':   mt_note,
        })

        # Зберігаємо external ID щоб уникнути дублів при повторному запуску
        env['ir.model.data'].sudo().create({
            'module':   '__import__',
            'model':    'mail.message',
            'name':     f'pipedrive_note_{note_id}',
            'res_id':   msg.id,
        })

        created += 1
        existing_notes.add(note_id)

    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f'  ПОМИЛКА (note {note_id}): {e}')

    if created % 1000 == 0 and created > 0:
        env.cr.commit()
        print(f'  Прогрес: {created+skipped_existing+skipped_no_target}/{len(df)} (створено: {created})')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Створено:          {created}')
print(f'Без прив\'язки:     {skipped_no_target}')
print(f'Вже існували:      {skipped_existing}')
print(f'Помилки:           {errors}')

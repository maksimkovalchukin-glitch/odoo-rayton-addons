"""
Фаза 5: Імпорт 277,811 активностей з Pipedrive → mail.message (chatter) в Odoo.

Завершені активності → запис в chatter (log) на угоді/контакті/компанії.
Пріоритет прив'язки: угода > контакт > організація

Типи активностей Pipedrive → іконка в тілі повідомлення:
  Телефонний дзвінок Клієнту → 📞
  Вихідний дзвінок            → 📞
  Вхідний дзвінок             → 📲
  Недозвон                    → 📵
  Завдання                    → ✅
  Надіслано лист/КП           → ✉️
  Онлайн-зустріч              → 🖥️
  інше                        → 📌

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/import_activities_phase5.py
"""
import pandas as pd
from datetime import datetime

ACTIVITIES_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/activities.xlsx'

TYPE_ICON = {
    'Телефонний дзвінок Клієнту':                   '📞',
    'Вихідний дзвінок':                              '📞',
    'Вхідний дзвінок':                               '📲',
    'Недозвон':                                      '📵',
    'Завдання':                                      '✅',
    'Обробка нових':                                 '🔄',
    'Надіслано лист/ КП✉️':                          '✉️',
    'Повернення картки на оператора колл-центру⏸️':  '⏸️',
    'Онлайн-зустріч':                                '🖥️',
    'vdguk_vd_klyenta_fdbek':                        '📋',
}

def clean_str(v):
    if pd.isna(v):
        return ''
    return str(v).strip()

print('=== Фаза 5: Імпорт активностей ===')
print('Читаємо activities.xlsx...')
df = pd.read_excel(ACTIVITIES_PATH)
print(f'Завантажено {len(df)} активностей')

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

# 3. pipedrive org_id → res.partner.id
imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'),
     ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
org_to_partner = {int(r['name'].replace('pipedrive_org_', '')): r['res_id'] for r in imd}
print(f'  {len(org_to_partner)} організацій в системі')

# 4. Користувачі
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

# 5. Subtype — внутрішня нотатка
mt_note = env.ref('mail.mt_note').id

# 6. Вже імпортовані
existing_acts = set()
imd_acts = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'mail.message'),
     ('name', 'like', 'pipedrive_act_')],
    ['name']
)
for r in imd_acts:
    try:
        existing_acts.add(int(r['name'].replace('pipedrive_act_', '')))
    except ValueError:
        pass
print(f'  {len(existing_acts)} вже імпортованих активностей')

# --- Основний цикл ---
created = 0
skipped_no_target = 0
skipped_existing = 0
errors = 0

for _, row in df.iterrows():
    act_id = int(row['Ідентифікатор'])

    if act_id in existing_acts:
        skipped_existing += 1
        continue

    # Визначаємо прив'язку: угода > контакт > організація
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
        date_raw = row.get('Дата виконання')
    if pd.isna(date_raw):
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(date_raw, str):
        date_str = date_raw[:19]
    else:
        try:
            date_str = date_raw.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            date_str = str(date_raw)[:19]

    act_type = clean_str(row.get('Тип'))
    icon = TYPE_ICON.get(act_type, '📌')
    subject = clean_str(row.get('Тема')) or act_type
    note = clean_str(row.get('Нотатка'))
    done = clean_str(row.get('Виконано')) == 'Виконано'
    assigned = clean_str(row.get('Призначено користувачеві'))

    author_pid = find_author(row.get('Автор') or row.get('Призначено користувачеві'))

    # Формуємо тіло повідомлення
    status = '✓' if done else '○'
    lines = [f'<strong>{icon} {act_type}</strong> {status}']
    if subject and subject != act_type:
        lines.append(f'<em>{subject}</em>')
    if assigned:
        lines.append(f'Виконавець: {assigned}')
    if note:
        lines.append(f'<br/>{note}')
    body = '<p>' + '<br/>'.join(lines) + '</p>'

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

        env['ir.model.data'].sudo().create({
            'module':   '__import__',
            'model':    'mail.message',
            'name':     f'pipedrive_act_{act_id}',
            'res_id':   msg.id,
        })

        created += 1
        existing_acts.add(act_id)

    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f'  ПОМИЛКА (act {act_id}): {e}')

    if created % 2000 == 0 and created > 0:
        env.cr.commit()
        print(f'  Прогрес: {created+skipped_existing+skipped_no_target}/{len(df)} (створено: {created})')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Створено:         {created}')
print(f'Без прив\'язки:    {skipped_no_target}')
print(f'Вже існували:     {skipped_existing}')
print(f'Помилки:          {errors}')

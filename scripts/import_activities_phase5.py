"""
Фаза 5 (v4): Імпорт активностей з Pipedrive → mail.message в Odoo.

Виправлення vs v3:
  - subtype_id = mail.mt_activities (виглядає як виконана дія, не як нотатка)
  - Ксенія Коваленко (Pipedrive) = Сущенко Оксана (Odoo) → ксенія коваленко: сущенко
  - author_id = Призначено (хто виконував)
  - Дедублікація: один запис на (target, дата, тип, виконавець)

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/import_activities_phase5.py
"""
import pandas as pd
from datetime import datetime

ACTIVITIES_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/activities.xlsx'

TYPE_ICON = {
    'Телефонний дзвінок Клієнту':                    '📞',
    'Вихідний дзвінок':                               '📞',
    'Вхідний дзвінок':                                '📲',
    'Недозвон':                                       '📵',
    'Завдання':                                       '✅',
    'Обробка нових':                                  '🔄',
    'Надіслано лист/ КП\u2709\ufe0f':                 '\u2709\ufe0f',
    'Повернення картки на оператора колл-центру\u23f8\ufe0f': '\u23f8\ufe0f',
    'Онлайн-зустріч':                                 '🖥️',
    'vdguk_vd_klyenta_fdbek':                         '📋',
}

# Маппінг автора Pipedrive → прізвище в Odoo (None = Admin)
AUTHOR_MAP = {
    'богдан безверхий':          None,
    'наталія гадайчук':          'гадайчук',
    'ігор бєлік':                None,
    'сергій толочко':            'толочко',
    'антон мазур':               None,
    'олександр достовалов':      'достовалов',
    'timur':                     None,
    'віталій стоцький':          'стоцький',
    'юрій лисенко':              'лисенко',
    'юрій ходаківський':         'ходаківський',
    'андрій селезньов':          'селезньов',
    'олександр пилипенко':       None,
    'андрій малиновський':       None,
    'ольга вергун':              None,
    'станіслав бобровицький':    'бобровицький',
    'павлов дмитро':             'павлов',
    'микола тубіш':              'тубіш',
    'ксенія коваленко':          'сущенко',   # Оксана Сущенко в Odoo
    'artem':                     None,
    'ольга':                     None,
    'анатолій купчин':           None,
    'максим сидоров':            'сидоров',
    'катерина манюхіна':         None,
    'яна курнаєва':              'курнаєва',
    'леся':                      'радіоненко',
    'юрій (дніпро)':             None,
    'ірина бакуменко':           'бакуменко',
    'микола':                    'тубіш',
    'дмитро':                    'яловенко',
    'олександр коростіль':       'коростіль',
    'сергій ничипоренко':        None,
    'дмитро петров':             'петров',
    'олександр умнов':           None,
    'роман':                     None,   # невідомий, → Admin
    'владислава карась':         None,   # невідома, → Admin
    'оксана сущенко':            'сущенко',   # запасне ім'я Ксенії Коваленко
}

def clean_str(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    return str(v).strip()

print('=== Фаза 5 v4: Імпорт активностей ===')

# --- Users ---
all_users = env['res.users'].search_read([('active', '=', True)], ['name', 'partner_id'])
admin_pid = env.ref('base.user_admin').partner_id.id

surname_to_pid = {}
for u in all_users:
    parts = u['name'].split()
    if parts:
        s = parts[0].replace('C', '\u0421').replace('c', '\u0441').lower()
        surname_to_pid[s] = u['partner_id'][0]

def get_author_pid(username):
    if not username:
        return admin_pid
    clean = str(username).split('/')[0].split('-')[0].split('|')[0].strip().lower()
    if clean in AUTHOR_MAP:
        surname = AUTHOR_MAP[clean]
        if surname is None:
            return admin_pid
        return surname_to_pid.get(surname, admin_pid)
    return admin_pid

# --- Видаляємо старі імпортовані активності ---
print('\n[1] Видалення старих activity messages...')
env.cr.execute("""
    SELECT res_id FROM ir_model_data
    WHERE module = '__import__'
      AND model = 'mail.message'
      AND name LIKE 'pipedrive_act_%'
""")
old_msg_ids = [r[0] for r in env.cr.fetchall()]
print(f'  Знайдено старих: {len(old_msg_ids)}')

if old_msg_ids:
    # Видаляємо батчами
    batch = 5000
    for i in range(0, len(old_msg_ids), batch):
        chunk = old_msg_ids[i:i+batch]
        env.cr.execute("DELETE FROM mail_message WHERE id = ANY(%s)", [chunk])
    env.cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = '__import__'
          AND model = 'mail.message'
          AND name LIKE 'pipedrive_act_%'
    """)
    env.cr.commit()
    print(f'  ✓ Видалено {len(old_msg_ids)} повідомлень')

# --- Subtype для виконаних активностей ---
mt_activities = env.ref('mail.mt_activities').id

# --- Довідники ---
print('\n[2] Завантаження довідників...')

deals = env['crm.lead'].search_read([('pipedrive_deal_id', '>', 0)], ['pipedrive_deal_id', 'id'])
deal_to_lead = {r['pipedrive_deal_id']: r['id'] for r in deals}
print(f'  {len(deal_to_lead)} угод')

persons = env['res.partner'].search_read([('pipedrive_person_id', '>', 0)], ['pipedrive_person_id', 'id'])
person_to_partner = {r['pipedrive_person_id']: r['id'] for r in persons}
print(f'  {len(person_to_partner)} контактів')

imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'), ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
org_to_partner = {int(r['name'].replace('pipedrive_org_', '')): r['res_id'] for r in imd}
print(f'  {len(org_to_partner)} організацій')

# --- Читаємо Excel ---
print('\n[3] Читаємо activities.xlsx...')
df = pd.read_excel(ACTIVITIES_PATH)
print(f'  {len(df)} рядків')

# --- Основний цикл ---
print('\n[4] Імпорт...')
created = 0
skipped_no_target = 0
skipped_dup = 0
errors = 0

# Ключ дедублікації: (res_model, res_id, date_day, type, assigned)
seen_keys = set()

for _, row in df.iterrows():
    act_id = int(row['Ідентифікатор'])

    # Визначаємо прив'язку
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
    date_raw = row.get('Час позначення як виконаного') or row.get('Час додавання') or row.get('Дата виконання')
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
    assigned = clean_str(row.get('Призначено користувачеві'))
    note = clean_str(row.get('Нотатка'))

    # Дедублікація: (модель, id, дата(дн), тип, виконавець)
    date_day = date_str[:10]
    dedup_key = (res_model, res_id, date_day, act_type, assigned)
    if dedup_key in seen_keys:
        skipped_dup += 1
        continue
    seen_keys.add(dedup_key)

    icon = TYPE_ICON.get(act_type, '📌')
    subject = clean_str(row.get('Тема')) or act_type
    done = clean_str(row.get('Виконано')) == 'Виконано'

    # Автор = хто створив в Pipedrive (часто Ольга/адмін)
    # Призначено = хто ВИКОНУВАВ активність — це правильний автор для чаттера
    author_pid = get_author_pid(row.get('Призначено користувачеві') or row.get('Автор'))

    # Тіло повідомлення
    status = '\u2713' if done else '\u25cb'
    lines = ['<strong>%s %s</strong> %s' % (icon, act_type, status)]
    if subject and subject != act_type:
        lines.append('<em>%s</em>' % subject)
    if assigned:
        lines.append('Виконавець: %s' % assigned)
    if note:
        lines.append('<br/>%s' % note)
    body = '<p>' + '<br/>'.join(lines) + '</p>'

    try:
        msg = env['mail.message'].sudo().create({
            'res_id':       res_id,
            'model':        res_model,
            'body':         body,
            'date':         date_str,
            'author_id':    author_pid,
            'message_type': 'comment',
            'subtype_id':   mt_activities,   # виглядає як виконана дія (Дії в чаттері)
        })

        env['ir.model.data'].sudo().create({
            'module':   '__import__',
            'model':    'mail.message',
            'name':     'pipedrive_act_%d' % act_id,
            'res_id':   msg.id,
        })

        created += 1

    except Exception as e:
        errors += 1
        if errors <= 5:
            print('  ПОМИЛКА (act %d): %s' % (act_id, e))

    if created % 5000 == 0 and created > 0:
        env.cr.commit()
        total = created + skipped_no_target + skipped_dup
        print('  Прогрес: %d/%d (створено: %d, дублі: %d)' % (total, len(df), created, skipped_dup))

env.cr.commit()
print('\n=== Готово ===')
print('Створено:           %d' % created)
print('Без прив\'язки:      %d' % skipped_no_target)
print('Дублі (пропущено):  %d' % skipped_dup)
print('Помилки:            %d' % errors)

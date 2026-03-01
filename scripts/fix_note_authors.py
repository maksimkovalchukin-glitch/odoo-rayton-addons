"""
Виправлення author_id для 19k+ нотаток з неправильним автором.

Причина помилки: find_author шукав по першому слову імені (напр. "Олександр")
і підбирав першого знайденого Odoo-юзера замість конкретного.

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/fix_note_authors.py
"""
import pandas as pd

NOTES_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/notes.xlsx'

print('=== Виправлення авторів нотаток ===')

# --- Правильний маппінг: ім'я з Pipedrive (до "/") → прізвище в Odoo ---
# None = Admin
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
    'ксенія коваленко':          None,
    'artem':                     None,
    'ольга':                     None,  # власник компанії → Admin
    'анатолій купчин':           None,
    'максим сидоров':            'сидоров',
    'катерина манюхіна':         None,  # ще не в Odoo → Admin (виправимо після додавання)
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
}

# --- Будуємо surname → partner_id з Odoo users ---
all_users = env['res.users'].search_read([('active', '=', True)], ['name', 'partner_id'])
admin_pid = env.ref('base.user_admin').partner_id.id

surname_to_pid = {}
for u in all_users:
    parts = u['name'].split()
    if parts:
        # Перше слово = прізвище (формат "Прізвище Ім'я По-батькові")
        # Нормалізуємо Latin C → Cyrillic С для Сидоров/Стоцький
        s = parts[0].replace('C', '\u0421').replace('c', '\u0441').lower()
        surname_to_pid[s] = u['partner_id'][0]

def get_correct_pid(pipedrive_username):
    """Повертає правильний partner_id за іменем з Pipedrive."""
    if not pipedrive_username or (isinstance(pipedrive_username, float)):
        return admin_pid
    clean = str(pipedrive_username).split('/')[0].split('-')[0].split('|')[0].strip().lower()
    if clean in AUTHOR_MAP:
        surname = AUTHOR_MAP[clean]
        if surname is None:
            return admin_pid
        pid = surname_to_pid.get(surname)
        return pid if pid else admin_pid
    # Невідомий автор → admin
    return admin_pid

# --- Читаємо notes.xlsx ---
print('Читаємо notes.xlsx...')
df = pd.read_excel(NOTES_PATH)
print(f'  {len(df)} нотаток')

# --- Завантажуємо маппінг pipedrive_note_id → mail.message.id ---
print('Завантажуємо ir.model.data...')
env.cr.execute("""
    SELECT name, res_id
    FROM ir_model_data
    WHERE module = '__import__'
      AND model = 'mail.message'
      AND name LIKE 'pipedrive_note_%'
""")
note_id_to_msg_id = {
    int(r[0].replace('pipedrive_note_', '')): r[1]
    for r in env.cr.fetchall()
}
print(f'  {len(note_id_to_msg_id)} нотаток в системі')

# --- Будуємо список виправлень: (message_id, correct_pid) ---
print('Будуємо список виправлень...')
fixes = []  # [(message_id, correct_pid)]

for _, row in df.iterrows():
    note_id = int(row['Ідентифікатор'])
    msg_id = note_id_to_msg_id.get(note_id)
    if not msg_id:
        continue

    correct_pid = get_correct_pid(row.get('\u041a\u043e\u0440\u0438\u0441\u0442\u0443\u0432\u0430\u0447'))
    fixes.append((msg_id, correct_pid))

print(f'  Нотаток для перевірки: {len(fixes)}')

# --- Перевіряємо поточних авторів і оновлюємо тільки неправильних ---
if not fixes:
    print('Нічого не виправляти!')
else:
    msg_ids = [f[0] for f in fixes]
    # Завантажуємо поточних авторів батчами
    env.cr.execute(
        "SELECT id, author_id FROM mail_message WHERE id = ANY(%s)",
        [msg_ids]
    )
    current_authors = {r[0]: r[1] for r in env.cr.fetchall()}

    # Формуємо реальні виправлення
    real_fixes = []
    for msg_id, correct_pid in fixes:
        current = current_authors.get(msg_id)
        if current != correct_pid:
            real_fixes.append((msg_id, correct_pid))

    print(f'  Нотаток з неправильним автором: {len(real_fixes)}')

    # Групуємо по correct_pid для batch UPDATE
    from collections import defaultdict
    by_pid = defaultdict(list)
    for msg_id, pid in real_fixes:
        by_pid[pid].append(msg_id)

    updated = 0
    for pid, ids in by_pid.items():
        env.cr.execute(
            "UPDATE mail_message SET author_id = %s WHERE id = ANY(%s)",
            [pid, ids]
        )
        updated += len(ids)
        # Отримуємо ім'я для логу
        env.cr.execute(
            "SELECT name FROM res_partner WHERE id = %s",
            [pid]
        )
        row = env.cr.fetchone()
        name = row[0] if row else 'RAYTON Admin'
        if isinstance(name, dict):
            name = name.get('uk_UA') or name.get('en_US') or str(name)
        print(f'  ✓ {name[:30]}: оновлено {len(ids)} нотаток')

    env.cr.commit()
    print(f'\nВсього оновлено: {updated} нотаток')

print('\n=== Готово ===')

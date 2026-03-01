"""
Прив'язує mail_activity_type_id до кожного activity-повідомлення в чаттері.
Це дозволяє фільтрувати та аналізувати активності за типами.

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/fix_activity_types.py
"""
import pandas as pd

ACTIVITIES_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/activities.xlsx'

print('=== Прив\'язка типів активностей ===')

# --- Крок 1: Отримуємо або створюємо всі потрібні типи ---
def get_or_create_type(name, icon):
    t = env['mail.activity.type'].search([('name', 'ilike', name)], limit=1)
    if not t:
        t = env['mail.activity.type'].create({
            'name': name,
            'icon': icon,
            'delay_count': 0,
            'delay_unit': 'days',
        })
        # Додаємо uk_UA переклад
        env.cr.execute(
            "UPDATE mail_activity_type SET name = name || %s WHERE id = %s",
            ['{"uk_UA": "%s"}' % name, t.id]
        )
        print(f'  Створено тип: {name} (id={t.id})')
    return t.id

# Базові типи (вже є в системі)
types_by_name = {}
for t in env['mail.activity.type'].search_read([], ['id', 'name']):
    raw = t['name']
    if isinstance(raw, dict):
        name_uk = raw.get('uk_UA') or raw.get('en_US') or ''
    else:
        name_uk = str(raw)
    types_by_name[name_uk.strip()] = t['id']

# Додаємо нові типи яких нема
needed_types = [
    ('Передача ліда',      'fa-exchange'),
    ('Обробка нових лідів','fa-filter'),
    ('Відправка ПКП',      'fa-file-text-o'),
]
for name, icon in needed_types:
    if name not in types_by_name:
        tid = get_or_create_type(name, icon)
        types_by_name[name] = tid

env.cr.commit()
print(f'  Всього типів: {len(types_by_name)}')

# --- Крок 2: Маппінг Pipedrive type → mail.activity.type.id ---
# Визначаємо ID для зручності
T = types_by_name
TYPE_MAP = {
    'Телефонний дзвінок Клієнту':                         T.get('Телефонний дзвінок Клієнту', 2),
    'Вихідний дзвінок':                                   T.get('Вихідний дзвінок', 2),
    'Вхідний дзвінок':                                    T.get('Вхідний дзвінок', 2),
    'Недозвон':                                           T.get('Недозвон', 18),
    'Пропущений дзвінок':                                 T.get('Недозвон', 18),
    'Телефонний дзвінок (партнерство Банк )':             T.get('Телефонний дзвінок Клієнту', 2),
    'Завдання':                                           T.get('Завдання КЦ', 4),
    'Завдання (реалізація проекту / взаємодія з технічним Департаментом)': T.get('Завдання КЦ', 4),
    'Обробка нових':                                      T.get('Обробка нових лідів', 4),
    'Повернення картки на оператора колл-центру\u23f8\ufe0f': T.get('Завдання КЦ', 4),
    'vdguk_vd_klyenta_fdbek':                             T.get('Завдання КЦ', 4),
    'priynyato_v_robotu':                                 T.get('Завдання КЦ', 4),
    'peredacha_kartki_na_mp__pk':                         T.get('Передача ліда', 4),
    'Надіслано лист/ КП\u2709\ufe0f':                    T.get('Надіслати КП', 22),
    'Відправка ПКП\u2709\ufe0f':                         T.get('Відправка ПКП', 22),
    'Відправка ПКП✉️':                                   T.get('Відправка ПКП', 22),
    'Онлайн-зустріч':                                     T.get('Онлайн-зустріч', 20),
    'Офлайн-зустріч з Клієнтом / Партнером':              T.get('Офлайн-зустріч', 21),
    'Передача картки на МП / ПКП новий лід\U0001f525':    T.get('Передача ліда', 4),
    'Передача картки на МП / ПКП старий лід\U0001f525':   T.get('Передача ліда', 4),
    'Передача картки на МВК':                             T.get('Передача ліда', 4),
    'Дублі та інше':                                      T.get('Завдання КЦ', 4),
    'Підготовка договору':                                T.get('Завдання КЦ', 4),
    'Проведення навчання, банк':                          T.get('Онлайн-зустріч', 20),
    'Ел. пошта':                                          T.get('Ел. пошта', 1),
    'Термін виконання':                                   T.get('Завдання КЦ', 4),
    'Невідповідний лід (повернення на КЦ)\u2639\ufe0f':   T.get('Завдання КЦ', 4),
    'lunch':                                              T.get('Завдання КЦ', 4),
}

print('\n--- Розподіл типів ---')
from collections import Counter
counter = Counter()

# --- Крок 3: Читаємо activities.xlsx і будуємо маппінг act_id → type_id ---
print('\n[1] Читаємо activities.xlsx...')
df = pd.read_excel(ACTIVITIES_PATH)
print(f'  {len(df)} рядків')

act_id_to_type = {}
for _, row in df.iterrows():
    act_id = int(row['Ідентифікатор'])
    act_type = str(row.get('Тип') or '').strip()
    type_id = TYPE_MAP.get(act_type)
    if type_id:
        act_id_to_type[act_id] = type_id
        counter[act_type] += 1

print(f'  {len(act_id_to_type)} активностей з відомим типом')

# --- Крок 4: Завантажуємо ir_model_data ext IDs ---
print('\n[2] Завантажуємо ir_model_data...')
env.cr.execute("""
    SELECT name, res_id FROM ir_model_data
    WHERE module = '__import__'
      AND model = 'mail.message'
      AND name LIKE 'pipedrive_act_%'
""")
ext_map = {r[0]: r[1] for r in env.cr.fetchall()}
print(f'  {len(ext_map)} повідомлень в Odoo')

# --- Крок 5: Групуємо updates по type_id і виконуємо batch UPDATE ---
print('\n[3] Оновлення mail_activity_type_id...')

from collections import defaultdict
by_type = defaultdict(list)  # type_id → [msg_id, ...]

for act_id, type_id in act_id_to_type.items():
    msg_id = ext_map.get('pipedrive_act_%d' % act_id)
    if msg_id:
        by_type[type_id].append(msg_id)

total_updated = 0
for type_id, msg_ids in by_type.items():
    # Batch UPDATE
    batch_size = 5000
    for i in range(0, len(msg_ids), batch_size):
        chunk = msg_ids[i:i+batch_size]
        env.cr.execute(
            "UPDATE mail_message SET mail_activity_type_id = %s WHERE id = ANY(%s)",
            [type_id, chunk]
        )
        total_updated += env.cr.rowcount
    env.cr.commit()
    type_name = [k for k, v in T.items() if v == type_id]
    tname = type_name[0] if type_name else str(type_id)
    print(f'  [{type_id}] {tname}: {len(msg_ids)} повідомлень')

print(f'\nВсього оновлено: {total_updated}')
print('=== Готово ===')

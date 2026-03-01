"""
Виправлення після фази 3:
1. Перейменовуємо crm.team: Колл-центр → Оператори, Відділ продажу → Менеджери
2. Призначаємо team_id=Менеджери для 608 угод без команди (Воронка Менеджер)
3. Виправляємо продавців Сидорова (89) та Стоцького (92) — були з латинською C

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/fix_deals_teams_owners.py
"""
import pandas as pd

print('=== Виправлення угод ===')

XLSX_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/deals.xlsx'

# --- 1. Перейменування команд ---
print('\n[1] Перейменування crm.team...')

kc_team = env['crm.team'].search([('name', 'ilike', 'Колл')], limit=1)
sales_team = env['crm.team'].search([('id', '=', 1)], limit=1)  # Sales / Відділ продажу

print(f'  Знайдено: kc_team={kc_team.name if kc_team else "НЕ ЗНАЙДЕНО"} (id={kc_team.id if kc_team else "-"})')
print(f'  Знайдено: sales_team={sales_team.name if sales_team else "НЕ ЗНАЙДЕНО"} (id={sales_team.id if sales_team else "-"})')

if kc_team:
    kc_team.write({'name': 'Оператори'})
    print(f'  ✓ {kc_team.id}: Колл-центр → Оператори')

if sales_team:
    sales_team.write({'name': 'Менеджери'})
    print(f'  ✓ {sales_team.id}: Відділ продажу → Менеджери')

env.cr.commit()

# --- 2. Призначаємо team_id для угод без команди (Воронка Менеджер) ---
print('\n[2] Призначення Менеджери для угод без команди...')

env.cr.execute("""
    UPDATE crm_lead
    SET team_id = %s
    WHERE team_id IS NULL
      AND active IN (true, false)
""", [sales_team.id if sales_team else 1])
updated_teams = env.cr.rowcount
env.cr.commit()
print(f'  ✓ Оновлено team_id: {updated_teams} угод')

# --- 3. Виправлення продавців Сидоров / Стоцький ---
print('\n[3] Виправлення продавців...')

# Знаходимо правильних users
env.cr.execute("""
    SELECT u.id, p.name
    FROM res_users u
    JOIN res_partner p ON p.id = u.partner_id
    WHERE u.active = true AND u.share = false
""")
all_users_raw = env.cr.fetchall()

# Будуємо маппінг по всіх словах (та їх lowercase-варіантах)
surname_to_uid = {}
for uid, name in all_users_raw:
    for part in name.split():
        # Нормалізуємо: замінюємо латинські C/c на кирилицю
        part_fixed = part.replace('C', 'С').replace('c', 'с')
        surname_to_uid[part_fixed.lower()] = uid

sidorov_uid = surname_to_uid.get('сидоров')
stotskyi_uid = surname_to_uid.get('стоцький')
print(f'  Сидоров user_id: {sidorov_uid}')
print(f'  Стоцький user_id: {stotskyi_uid}')

admin_uid = env.ref('base.user_admin').id

# Читаємо Excel
df = pd.read_excel(XLSX_PATH)

# Знаходимо всі угоди Сидорова і Стоцького з Excel
sidorov_deals = []
stotskyi_deals = []

for _, row in df.iterrows():
    owner = str(row.get('Власник', '') or '')
    pd_id = int(row['Ідентифікатор'])

    owner_lower = owner.lower()
    if 'сидоров' in owner_lower:
        sidorov_deals.append(pd_id)
    elif 'стоцький' in owner_lower or 'стоцкий' in owner_lower:
        stotskyi_deals.append(pd_id)

print(f'  Угод Сидорова в Excel: {len(sidorov_deals)}')
print(f'  Угод Стоцького в Excel: {len(stotskyi_deals)}')

fixed = 0
for uid, pd_ids, label in [
    (sidorov_uid, sidorov_deals, 'Сидоров'),
    (stotskyi_uid, stotskyi_deals, 'Стоцький'),
]:
    if not uid or not pd_ids:
        continue

    env.cr.execute("""
        UPDATE crm_lead
        SET user_id = %s
        WHERE pipedrive_deal_id = ANY(%s)
          AND user_id = %s
    """, [uid, pd_ids, admin_uid])
    cnt = env.cr.rowcount
    fixed += cnt
    print(f'  ✓ {label}: виправлено {cnt} угод → user_id={uid}')

env.cr.commit()
print(f'\n  Всього виправлено продавців: {fixed}')

# --- Підсумок ---
env.cr.execute("""
    SELECT t.id, t.name->>'uk_UA', count(l.id)
    FROM crm_team t
    LEFT JOIN crm_lead l ON l.team_id = t.id
    WHERE t.id IN (1, 5, 6)
    GROUP BY t.id, t.name->>'uk_UA'
    ORDER BY t.id
""")
print('\n=== Розподіл по командах ===')
for row in env.cr.fetchall():
    print(f'  team_id={row[0]} ({row[1]}): {row[2]} угод')

print('\n=== Готово ===')

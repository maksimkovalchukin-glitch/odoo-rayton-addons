"""
Очищення:
1. Видаляємо стаціонарні (міські) номери з res.partner.phone
2. Встановлюємо lang=uk_UA для всіх партнерів (не користувачів)

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/cleanup_phones_lang.py
"""
print('=== Очищення: стаціонарні телефони + мова ===')

MOBILE_OPS = {'50','63','66','67','68','73','91','93','95','96','97','98','99'}

# --- 1. Видаляємо стаціонарні номери ---
print('\n[1] Видалення стаціонарних номерів...')

# Знаходимо всі телефони де оператор НЕ мобільний
env.cr.execute("SELECT id, phone FROM res_partner_phone")
rows = env.cr.fetchall()

landline_ids = []
for pid, phone in rows:
    if phone and len(phone) >= 5:
        op = phone[3:5]  # 380XX... → беремо цифри 4-5
        if op not in MOBILE_OPS:
            landline_ids.append(pid)

print(f'  Знайдено стаціонарних: {len(landline_ids)}')

if landline_ids:
    # Видаляємо батчами
    batch = 1000
    deleted = 0
    for i in range(0, len(landline_ids), batch):
        chunk = landline_ids[i:i+batch]
        env.cr.execute(
            "DELETE FROM res_partner_phone WHERE id = ANY(%s)",
            [chunk]
        )
        deleted += len(chunk)
    env.cr.commit()
    print(f'  Видалено: {deleted}')

# --- 2. Встановлюємо uk_UA для всіх партнерів без мови ---
print('\n[2] Встановлення мови uk_UA...')
env.cr.execute("""
    UPDATE res_partner
    SET lang = 'uk_UA'
    WHERE (lang IS NULL OR lang != 'uk_UA')
      AND id NOT IN (SELECT partner_id FROM res_users WHERE active = true)
""")
updated_lang = env.cr.rowcount
env.cr.commit()
print(f'  Оновлено партнерів: {updated_lang}')

# --- 3. Перераховуємо primary_phone після видалення стаціонарних ---
print('\n[3] Перерахунок primary_phone...')
# Знаходимо партнерів у яких зникли всі телефони після видалення стаціонарних
env.cr.execute("""
    UPDATE res_partner SET primary_phone = NULL
    WHERE primary_phone IS NOT NULL
      AND id NOT IN (SELECT DISTINCT partner_id FROM res_partner_phone)
""")
cleared = env.cr.rowcount
env.cr.commit()
print(f'  Очищено primary_phone (без телефонів): {cleared}')

print('\n=== Готово ===')

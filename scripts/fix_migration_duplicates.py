"""
Виправлення аномалій після міграції Pipedrive → Odoo

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf \
      -d 2xqjwr7pzvj.cloudpepper.site --no-http \
      < extra-addons/scripts/fix_migration_duplicates.py

Виправлення:
  1. Дублі pipedrive_person_id — залишаємо "кращий" запис (з company або з меншим ID)
  2. Телефони 80XXXXXXXXX (11 цифр) → 380XXXXXXXXX
"""

print('=== Fix: Аномалії після міграції ===')

# ── Fix 1: Дублі pipedrive_person_id ─────────────────────────────────────────
print('\n[1] Дублі pipedrive_person_id...')

# Знайти всі дублі — групуємо по person_id
dup_sql = """
SELECT pipedrive_person_id, array_agg(id ORDER BY (parent_id IS NOT NULL) DESC, id ASC) AS ids
FROM res_partner
WHERE pipedrive_person_id > 0 AND active = true
GROUP BY pipedrive_person_id
HAVING count(*) > 1
"""
env.cr.execute(dup_sql)
dup_rows = env.cr.fetchall()
print(f'  Знайдено дублів: {len(dup_rows)} пар')

fixed_dups = 0
errors_dup = 0

for pd_id, ids in dup_rows:
    keep_id = ids[0]   # кращий: першим сортується parent_id NOT NULL → менший ID
    del_ids  = ids[1:] # гірші

    for del_id in del_ids:
        try:
            env.cr.execute('SAVEPOINT sp_dup')

            # Перемістити телефони з "гіршого" до "кращого" (уникати дублів)
            env.cr.execute("""
                UPDATE res_partner_phone src
                SET partner_id = %s
                WHERE src.partner_id = %s
                  AND NOT EXISTS (
                    SELECT 1 FROM res_partner_phone ex
                    WHERE ex.partner_id = %s AND ex.phone = src.phone
                  )
            """, (keep_id, del_id, keep_id))

            # Видалити залишкові (дублі) телефони гіршого
            env.cr.execute("DELETE FROM res_partner_phone WHERE partner_id = %s", (del_id,))

            # Архівувати гірший запис (active=false), не hard-delete щоб не порушити FK
            env.cr.execute(
                "UPDATE res_partner SET active=false WHERE id=%s",
                (del_id,)
            )

            env.cr.execute('RELEASE SAVEPOINT sp_dup')
            fixed_dups += 1

        except Exception as e:
            env.cr.execute('ROLLBACK TO SAVEPOINT sp_dup')
            errors_dup += 1
            if errors_dup <= 5:
                print(f'  ПОМИЛКА (pd_id={pd_id}, del={del_id}): {e}')

env.cr.commit()
print(f'  Виправлено дублів: {fixed_dups}  Помилок: {errors_dup}')

# ── Fix 2: Телефони 80XXXXXXXXX → 380XXXXXXXXX ────────────────────────────────
print('\n[2] Телефони 80XXXXXXXXX (11 цифр) → 380XXXXXXXXX...')

# Знайти кандидатів
env.cr.execute("""
    SELECT id, phone, partner_id
    FROM res_partner_phone
    WHERE length(phone) = 11 AND phone LIKE '80%'
""")
phone_rows = env.cr.fetchall()
print(f'  Кандидатів: {len(phone_rows)}')

fixed_phones = 0
skipped_phones = 0
errors_phones = 0

for ph_id, phone, partner_id in phone_rows:
    new_phone = '3' + phone  # 80... → 380...

    # Перевірити чи новий номер вже є у цього партнера
    env.cr.execute("""
        SELECT 1 FROM res_partner_phone
        WHERE partner_id = %s AND phone = %s AND id != %s
    """, (partner_id, new_phone, ph_id))

    if env.cr.fetchone():
        # Вже є — видалити старий (дублікат)
        try:
            env.cr.execute('SAVEPOINT sp_ph2')
            env.cr.execute("DELETE FROM res_partner_phone WHERE id = %s", (ph_id,))
            env.cr.execute('RELEASE SAVEPOINT sp_ph2')
            skipped_phones += 1
        except Exception as e:
            env.cr.execute('ROLLBACK TO SAVEPOINT sp_ph2')
            errors_phones += 1
    else:
        # Оновити до правильного формату
        try:
            env.cr.execute('SAVEPOINT sp_ph3')
            env.cr.execute("UPDATE res_partner_phone SET phone = %s WHERE id = %s", (new_phone, ph_id))
            env.cr.execute('RELEASE SAVEPOINT sp_ph3')
            fixed_phones += 1
        except Exception as e:
            env.cr.execute('ROLLBACK TO SAVEPOINT sp_ph3')
            errors_phones += 1
            if errors_phones <= 5:
                print(f'  ПОМИЛКА (ph_id={ph_id}): {e}')

env.cr.commit()
print(f'  Оновлено: {fixed_phones}  Видалено дублів: {skipped_phones}  Помилок: {errors_phones}')

# ── Підсумок ──────────────────────────────────────────────────────────────────
print('\n=== Готово ===')
print(f'Дублі person_id виправлено: {fixed_dups}')
print(f'Телефони 80→380 виправлено: {fixed_phones}')
print(f'Телефони 80→380 (дубль, видалено): {skipped_phones}')

# Фінальна перевірка
env.cr.execute("""
    SELECT count(*) FROM (
        SELECT pipedrive_person_id FROM res_partner
        WHERE pipedrive_person_id > 0 AND active=true
        GROUP BY 1 HAVING count(*)>1
    ) x
""")
remaining_dups = env.cr.fetchone()[0]
print(f'Залишилось дублів person_id: {remaining_dups}')

env.cr.execute("SELECT count(*) FROM res_partner_phone WHERE length(phone)=11 AND phone LIKE '80%'")
remaining_phones = env.cr.fetchone()[0]
print(f'Залишилось телефонів 80... (11 цифр): {remaining_phones}')

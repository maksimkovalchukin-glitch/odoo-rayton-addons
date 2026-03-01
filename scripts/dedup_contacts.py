"""
Дедублікація контактів: видаляємо дублі що виникли в фазі 2b.
Стратегія: залишаємо старіший запис (менший ID), переносимо
pipedrive_person_id на нього, дублікат видаляємо.

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/dedup_contacts.py
"""
print('=== Дедублікація контактів ===')

# Знаходимо всі групи дублів: однаковий primary phone + одна компанія
env.cr.execute("""
    SELECT array_agg(p.id ORDER BY p.id) AS partner_ids
    FROM res_partner_phone ph
    JOIN res_partner p ON p.id = ph.partner_id
    WHERE p.active = true
      AND ph.is_primary = true
      AND p.parent_id IS NOT NULL
    GROUP BY ph.phone, p.parent_id
    HAVING COUNT(*) > 1
""")
groups = env.cr.fetchall()
print(f'Груп дублів: {len(groups)}')

merged = 0
errors = 0

for (partner_ids,) in groups:
    # Перший (менший ID) — залишаємо, решта — видаляємо
    keep_id = partner_ids[0]
    dup_ids = partner_ids[1:]

    keep = env['res.partner'].browse(keep_id)

    for dup_id in dup_ids:
        dup = env['res.partner'].browse(dup_id)

        try:
            # Переносимо pipedrive_person_id якщо у старого немає
            if not keep.pipedrive_person_id and dup.pipedrive_person_id:
                keep.pipedrive_person_id = dup.pipedrive_person_id

            # Переносимо mail.message з дубля на оригінал
            env.cr.execute(
                "UPDATE mail_message SET res_id = %s WHERE model = 'res.partner' AND res_id = %s",
                [keep_id, dup_id]
            )

            # Переносимо mail.activity
            env.cr.execute(
                "UPDATE mail_activity SET res_id = %s WHERE res_model = 'res.partner' AND res_id = %s",
                [keep_id, dup_id]
            )

            # Переносимо телефони яких нема у keep (щоб не дублювати)
            keep_phones = set(keep.phone_ids.mapped('phone'))
            for ph in dup.phone_ids:
                if ph.phone not in keep_phones:
                    ph.partner_id = keep_id
                    keep_phones.add(ph.phone)

            # Видаляємо дублікат
            dup.unlink()
            merged += 1

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f'  ПОМИЛКА (dup {dup_id} → keep {keep_id}): {e}')

    if merged % 500 == 0 and merged > 0:
        env.cr.commit()
        print(f'  Оброблено: {merged}')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Видалено дублів: {merged}')
print(f'Помилки:         {errors}')

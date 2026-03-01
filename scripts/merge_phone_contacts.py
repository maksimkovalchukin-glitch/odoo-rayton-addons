"""
Переносимо телефони з sub-контактів "Телефон організації" / "Телефон з фінансової звітності"
на батьківську компанію і видаляємо ці sub-контакти.

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/merge_phone_contacts.py
"""
import re

print('=== Перенос телефонів з sub-контактів на компанію ===')

PHONE_SUBCONTACT_NAMES = [
    'Телефон організації',
    'Телефон з фінансової звітності',
    'Телефон фінансової звітності',
    'Телефон фінансвої звітності',
    'Телефон',
    'Телефон оганізації',
    'Телефон фінансової організації',
    'Телефон організаці',
    'телефони',
    'телефон організації Бугалтерія',
]

# Знаходимо назву → тип телефону
def get_phone_type(name):
    n = (name or '').lower()
    if 'фінанс' in n:
        return 'fin'
    return 'org'

# Знаходимо всі такі sub-контакти
env.cr.execute("""
    SELECT id, name, parent_id
    FROM res_partner
    WHERE active = true
      AND parent_id IS NOT NULL
      AND name ILIKE ANY(ARRAY[
        'Телефон організації', 'Телефон з фінансової звітності',
        'Телефон фінансової звітності', 'Телефон фінансвої звітності',
        'Телефон', 'Телефон оганізації', 'Телефон фінансової організації',
        'Телефон організаці', 'телефони', 'телефон організації Бугалтерія'
      ])
""")
rows = env.cr.fetchall()
print(f'Знайдено sub-контактів для переносу: {len(rows)}')

merged = 0
no_phone = 0
errors = 0

for (partner_id, name, parent_id) in rows:
    sub = env['res.partner'].browse(partner_id)
    parent = env['res.partner'].browse(parent_id)

    if not sub.exists() or not parent.exists():
        continue

    phones = sub.phone_ids
    if not phones:
        # Перевіримо стандартні поля
        no_phone += 1
        try:
            sub.active = False
        except Exception:
            pass
        continue

    # Отримуємо вже існуючі номери компанії
    existing_phones = set(parent.phone_ids.mapped('phone'))
    ptype = get_phone_type(name)

    try:
        for ph in phones:
            if ph.phone and ph.phone not in existing_phones:
                env['res.partner.phone'].create({
                    'partner_id': parent_id,
                    'phone': ph.phone,
                    'phone_type': ptype,
                    'is_primary': False,
                })
                existing_phones.add(ph.phone)

        # Переносимо повідомлення на компанію
        env.cr.execute(
            "UPDATE mail_message SET res_id = %s WHERE model = 'res.partner' AND res_id = %s",
            [parent_id, partner_id]
        )

        # Видаляємо sub-контакт
        sub.unlink()
        merged += 1

    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f'  ПОМИЛКА (id={partner_id}): {e}')

    if merged % 1000 == 0 and merged > 0:
        env.cr.commit()
        print(f'  Перенесено: {merged}')

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Перенесено і видалено: {merged}')
print(f'Без телефону (архівовано): {no_phone}')
print(f'Помилки: {errors}')

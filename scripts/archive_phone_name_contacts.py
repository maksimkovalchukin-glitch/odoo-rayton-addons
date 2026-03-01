"""
Архівуємо контакти у яких ім'я = телефонний номер (сміттєві дані з Pipedrive).
"""
import re
print('Архівуємо контакти з номером як іменем...')

env.cr.execute("""
    UPDATE res_partner SET active = false
    WHERE active = true
      AND name ~ '^[0-9+() \\-]{7,}$'
      AND id NOT IN (SELECT partner_id FROM res_users WHERE active = true)
""")
count = env.cr.rowcount
env.cr.commit()
print(f'Архівовано: {count}')

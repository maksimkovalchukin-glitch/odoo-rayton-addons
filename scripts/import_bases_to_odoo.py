"""
Фаза 2 (сервер, Odoo shell): Імпорт підготовлених CSV в Odoo.

Читає:
  - /tmp/new_leads.csv         — нові ліди (компанії зі споживанням, яких нема в Odoo)
  - /tmp/enrich_partners.csv   — збагачення наявних контактів

Що робить:
  - new_leads: створює res.partner (компанія) + crm.lead (Розбір, Оператори)
  - enrich: заповнює порожні phone/email/region в res.partner

Запуск на сервері:
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf \\
      -d 2xqjwr7pzvj.cloudpepper.site --no-http \\
      < extra-addons/scripts/import_bases_to_odoo.py
"""

import csv
import os

CSV_NEW_LEADS = '/tmp/new_leads.csv'
CSV_ENRICH    = '/tmp/enrich_partners.csv'

# Стадія Розбір (перша КЦ-стадія, is_manager_pipeline=False)
kc_stage = env['crm.stage'].search(
    [('is_manager_pipeline', '=', False)], order='sequence', limit=1
)
kc_team_id = kc_stage.team_id.id if kc_stage else False
print(f'КЦ стадія: [{kc_stage.id}] {kc_stage.name}, team_id={kc_team_id}')


# ────────────────────────────────────────────────────────────────────────────────
# Частина 1: Нові ліди
# ────────────────────────────────────────────────────────────────────────────────
print(f'\n=== Частина 1: Нові ліди ({CSV_NEW_LEADS}) ===')

if not os.path.exists(CSV_NEW_LEADS):
    print('  ФАЙЛ НЕ ЗНАЙДЕНО — пропускаємо')
else:
    with open(CSV_NEW_LEADS, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    print(f'  Рядків у CSV: {len(rows)}')

    created_partners = 0
    created_leads    = 0
    skipped          = 0
    errors           = 0

    for i, row in enumerate(rows):
        edrpou = (row.get('edrpou') or '').strip()
        name   = (row.get('name') or '').strip()
        if not edrpou or not name:
            skipped += 1
            continue

        try:
            env.cr.execute('SAVEPOINT sp_lead')

            # Перевірка: раптом вже з'явився в Odoo між запусками
            existing = env['res.partner'].search([('vat', '=', edrpou), ('is_company', '=', True)], limit=1)
            if existing:
                skipped += 1
                env.cr.execute('RELEASE SAVEPOINT sp_lead')
                continue

            # Нормалізуємо числові поля
            mwh = row.get('mwh_month', '')
            try:
                mwh_val = float(mwh) if mwh else 0.0
            except ValueError:
                mwh_val = 0.0

            # Створюємо компанію
            partner_vals = {
                'name':       name,
                'is_company': True,
                'vat':        edrpou,
                'type':       'contact',
            }
            if row.get('phone'):
                partner_vals['phone'] = row['phone']
            if row.get('email'):
                partner_vals['email'] = row['email']
            if row.get('city'):
                partner_vals['city'] = str(row['city'])[:64]
            # Область → state_id (пошук за назвою)
            if row.get('region'):
                state = env['res.country.state'].search(
                    [('name', 'ilike', str(row['region'])[:20]), ('country_id.code', '=', 'UA')],
                    limit=1
                )
                if state:
                    partner_vals['state_id'] = state.id
                    partner_vals['country_id'] = state.country_id.id

            partner = env['res.partner'].create(partner_vals)
            created_partners += 1

            # Назва ліда: "Назва (споживання МВт/міс)"
            lead_name = name
            if mwh_val >= 1:
                lead_name = f'{name} ({mwh_val:.0f} МВт/міс)'

            # Будуємо опис
            desc_parts = []
            if row.get('sphere'):
                desc_parts.append(f'Сфера: {row["sphere"]}')
            if row.get('contact_person'):
                desc_parts.append(f'Контактна особа: {row["contact_person"]}')
            if row.get('director'):
                desc_parts.append(f'Директор: {row["director"]}')
            if row.get('address'):
                desc_parts.append(f'Адреса: {row["address"]}')

            lead_vals = {
                'name':       lead_name,
                'partner_id': partner.id,
                'type':       'lead',
                'team_id':    kc_team_id,
                'stage_id':   kc_stage.id if kc_stage else False,
                'description': '\n'.join(desc_parts) if desc_parts else False,
            }
            # Споживання в кастомне поле (якщо є)
            if mwh_val > 0 and hasattr(env['crm.lead'], 'consumption'):
                lead_vals['consumption'] = round(mwh_val, 2)

            env['crm.lead'].create(lead_vals)
            created_leads += 1

            env.cr.execute('RELEASE SAVEPOINT sp_lead')

        except Exception as e:
            env.cr.execute('ROLLBACK TO SAVEPOINT sp_lead')
            errors += 1
            if errors <= 5:
                print(f'  ПОМИЛКА (ЄДРПОУ={edrpou}): {e}')

        if (i + 1) % 50 == 0:
            env.cr.commit()
            print(f'  Оброблено {i+1}/{len(rows)} | Створено: {created_leads} лідів')

    env.cr.commit()
    print(f'\n  ✅ Нові ліди:')
    print(f'     Партнерів створено: {created_partners}')
    print(f'     Лідів створено:     {created_leads}')
    print(f'     Пропущено:          {skipped}')
    print(f'     Помилок:            {errors}')


# ────────────────────────────────────────────────────────────────────────────────
# Частина 2: Збагачення наявних контактів
# ────────────────────────────────────────────────────────────────────────────────
print(f'\n=== Частина 2: Збагачення контактів ({CSV_ENRICH}) ===')

if not os.path.exists(CSV_ENRICH):
    print('  ФАЙЛ НЕ ЗНАЙДЕНО — пропускаємо')
else:
    with open(CSV_ENRICH, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    print(f'  Рядків у CSV: {len(rows)}')

    updated_phone  = 0
    updated_email  = 0
    updated_city   = 0
    skipped        = 0
    errors         = 0

    for i, row in enumerate(rows):
        edrpou = (row.get('edrpou') or '').strip()
        if not edrpou:
            skipped += 1
            continue

        try:
            env.cr.execute('SAVEPOINT sp_enrich')

            partners = env['res.partner'].search(
                [('vat', '=', edrpou), ('is_company', '=', True), ('active', '=', True)],
                limit=1
            )
            if not partners:
                skipped += 1
                env.cr.execute('RELEASE SAVEPOINT sp_enrich')
                continue

            partner = partners
            vals = {}

            # Дописуємо тільки порожні поля (не перезаписуємо)
            if row.get('phone') and not partner.phone:
                vals['phone'] = row['phone']
                updated_phone += 1
            if row.get('email') and not partner.email:
                vals['email'] = row['email']
                updated_email += 1
            if row.get('city') and not partner.city:
                vals['city'] = str(row['city'])[:64]
                updated_city += 1
            if row.get('region') and not partner.state_id:
                state = env['res.country.state'].search(
                    [('name', 'ilike', str(row['region'])[:20]), ('country_id.code', '=', 'UA')],
                    limit=1
                )
                if state:
                    vals['state_id'] = state.id
                    if not partner.country_id:
                        vals['country_id'] = state.country_id.id

            if vals:
                partner.write(vals)

            env.cr.execute('RELEASE SAVEPOINT sp_enrich')

        except Exception as e:
            env.cr.execute('ROLLBACK TO SAVEPOINT sp_enrich')
            errors += 1
            if errors <= 5:
                print(f'  ПОМИЛКА (ЄДРПОУ={edrpou}): {e}')

        if (i + 1) % 500 == 0:
            env.cr.commit()
            print(f'  Оброблено {i+1}/{len(rows)} | phone={updated_phone} email={updated_email} city={updated_city}')

    env.cr.commit()
    print(f'\n  ✅ Збагачення завершено:')
    print(f'     Телефонів додано: {updated_phone}')
    print(f'     Email додано:     {updated_email}')
    print(f'     Міст додано:      {updated_city}')
    print(f'     Пропущено:        {skipped}')
    print(f'     Помилок:          {errors}')

print('\n=== ВСЕ ГОТОВО ===')

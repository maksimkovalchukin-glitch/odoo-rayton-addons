"""
Фаза 2 (API): Повний імпорт осіб (People) з Pipedrive API → Odoo res.partner

Різниця від import_people_phase2.py (Excel):
  - Пагінує Pipedrive REST API замість Excel файлу
  - Приймає ВСІ типи телефонів (не тільки мобільні)
  - Імпортує осіб навіть без телефону/email (якщо є ім'я)
  - Виявляє кастомні поля через /v1/personFields

Дедупліакція (не роби дублів):
  1. pipedrive_person_id вже є в Odoo → skip
  2. Телефон вже є у контакта тієї ж компанії → skip

Запуск на сервері:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf \
      -d 2xqjwr7pzvj.cloudpepper.site --no-http \
      < extra-addons/scripts/import_people_phase2_api.py
"""
import re
import time
import requests as _requests

PD_TOKEN  = '6e2c76ff5e6e56a2e88ac4bed5e88130c9d55cf4'
PD_BASE   = 'https://api.pipedrive.com/v1'
PAGE_SIZE = 500       # max allowed by Pipedrive
SLEEP_S   = 0.25     # seconds between pages (4 req/s — well under 10 req/s limit)
COMMIT_EVERY = 500   # commit DB transaction every N processed records

# ── Phone helpers ──────────────────────────────────────────────────────────────

def normalize_phone(raw):
    """Strip non-digits, fix Ukrainian prefix. Returns digits-only string."""
    d = re.sub(r'[^\d]', '', str(raw or ''))
    if len(d) == 10 and d.startswith('0'):
        d = '380' + d[1:]
    return d or None

def pd_label_to_type(label):
    """Map Pipedrive phone label → res.partner.phone phone_type."""
    lbl = (label or '').lower()
    if 'мобіл' in lbl or 'mobile' in lbl or 'cell' in lbl:
        return 'mobile'
    if 'робоч' in lbl or 'work' in lbl or 'office' in lbl:
        return 'work'
    if 'прям' in lbl or 'direct' in lbl:
        return 'direct'
    if 'особист' in lbl or 'personal' in lbl:
        return 'personal'
    return 'other'

# ── Discover Pipedrive custom field keys ───────────────────────────────────────
print('=== Фаза 2 (API): Повний імпорт контактів з Pipedrive ===')
print('Отримуємо кастомні поля PersonFields...')

cf_resp = _requests.get(
    f'{PD_BASE}/personFields',
    params={'api_token': PD_TOKEN, 'limit': 200},
    timeout=20,
).json()

cf_key_посада   = None
cf_key_примітка = None
cf_key_група    = None
cf_opts_посада  = {}   # option_id (str) → label
cf_opts_група   = {}

for f in (cf_resp.get('data') or []):
    fname = f.get('name', '')
    fkey  = f.get('key', '')
    opts  = {str(o['id']): o['label'] for o in (f.get('options') or [])}
    if fname == 'Посада':
        cf_key_посада  = fkey
        cf_opts_посада = opts
        print(f'  Посада → {fkey} ({len(opts)} variants)')
    elif fname == 'Примітка':
        cf_key_примітка = fkey
        print(f'  Примітка → {fkey}')
    elif 'рийняття рішень' in fname or fname == 'Група':
        cf_key_група  = fkey
        cf_opts_група = opts
        print(f'  Група прийняття рішень → {fkey} ({len(opts)} variants)')

if not cf_key_посада:
    print('  [!] Кастомне поле "Посада" не знайдено — використовуємо job_title')
if not cf_key_примітка:
    print('  [!] Кастомне поле "Примітка" не знайдено')

# ── Load Odoo lookups ──────────────────────────────────────────────────────────

print('Завантажуємо org external IDs (ir.model.data)...')
imd_rows = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'),
     ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id'],
)
org_to_odoo = {}
for rec in imd_rows:
    try:
        pd_org_id = int(rec['name'].replace('pipedrive_org_', ''))
        org_to_odoo[pd_org_id] = rec['res_id']
    except ValueError:
        pass
print(f'  {len(org_to_odoo)} org external IDs завантажено')

print('Завантажуємо вже імпортовані person IDs...')
rows_existing = env['res.partner'].search_read(
    [('pipedrive_person_id', '>', 0)],
    ['pipedrive_person_id'],
)
existing_person_ids = {r['pipedrive_person_id'] for r in rows_existing}
print(f'  {len(existing_person_ids)} осіб вже в Odoo')

print('Завантажуємо існуючі телефони в res.partner.phone...')
existing_phones = {}  # phone (digits) → set of partner_ids
for ph in env['res.partner.phone'].search_read([], ['phone', 'partner_id']):
    if ph['phone']:
        existing_phones.setdefault(ph['phone'], set()).add(ph['partner_id'][0])
print(f'  {len(existing_phones)} унікальних телефонів в системі')

# ── Main import loop ───────────────────────────────────────────────────────────

print('\nПочинаємо пагінацію Pipedrive /persons...')

created          = 0
skipped_existing = 0
skipped_noname   = 0
merged_phone     = 0
errors           = 0
commit_counter   = 0

start      = 0
total_pd   = None
page_num   = 0

while True:
    resp = _requests.get(
        f'{PD_BASE}/persons',
        params={'api_token': PD_TOKEN, 'start': start, 'limit': PAGE_SIZE},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f'  ПОМИЛКА HTTP {resp.status_code}: {resp.text[:200]} — зупиняємось')
        break

    data  = resp.json()
    items = data.get('data') or []
    page_num += 1

    if total_pd is None:
        pag = data.get('additional_data', {}).get('pagination', {})
        total_pd = pag.get('total_count', '?')
        print(f'  Всього в Pipedrive: {total_pd}')

    if not items:
        break

    for person in items:
        pd_id = person.get('id')
        if not pd_id:
            continue

        # ── 1. Skip if already imported ────────────────────────────────────────
        if pd_id in existing_person_ids:
            skipped_existing += 1
            commit_counter += 1
            continue

        # ── 2. Name required ───────────────────────────────────────────────────
        name = (person.get('name') or '').strip()
        if not name:
            skipped_noname += 1
            commit_counter += 1
            continue

        # ── 3. Phones ──────────────────────────────────────────────────────────
        phone_entries = []
        primary_set   = False
        for ph_obj in (person.get('phone') or []):
            raw_val = (ph_obj.get('value') or '').strip()
            if not raw_val:
                continue
            norm = normalize_phone(raw_val)
            if not norm:
                continue
            is_primary = bool(ph_obj.get('primary') and not primary_set)
            if is_primary:
                primary_set = True
            phone_entries.append({
                'phone': norm,
                'phone_type': pd_label_to_type(ph_obj.get('label', '')),
                'is_primary': is_primary,
            })
        if phone_entries and not primary_set:
            phone_entries[0]['is_primary'] = True

        # ── 4. Email ───────────────────────────────────────────────────────────
        email = ''
        for em in (person.get('email') or []):
            v = (em.get('value') or '').strip()
            if v and '@' in v:
                email = v
                break

        # ── 5. Company (parent) ────────────────────────────────────────────────
        org_data  = person.get('org_id')
        pd_org_id = org_data.get('value') if isinstance(org_data, dict) else org_data
        parent_id = org_to_odoo.get(int(pd_org_id)) if pd_org_id else False

        # ── 6. Phone dedup within same company ────────────────────────────────
        if parent_id and phone_entries:
            is_phone_dup = False
            for ph_entry in phone_entries:
                norm_ph = ph_entry['phone']
                if norm_ph in existing_phones:
                    sibs = env['res.partner'].browse(
                        list(existing_phones[norm_ph])
                    ).filtered(lambda p: p.parent_id.id == parent_id)
                    if sibs:
                        is_phone_dup = True
                        break
            if is_phone_dup:
                merged_phone += 1
                existing_person_ids.add(pd_id)
                commit_counter += 1
                continue

        # ── 7. Custom fields ───────────────────────────────────────────────────
        function_val = ''
        if cf_key_посада and person.get(cf_key_посада):
            opt_id = str(person[cf_key_посада])
            function_val = cf_opts_посада.get(opt_id, opt_id)
        if not function_val:
            function_val = (person.get('job_title') or '').strip()

        comment_val = ''
        if cf_key_примітка and person.get(cf_key_примітка):
            comment_val = str(person[cf_key_примітка]).strip()

        if cf_key_група and person.get(cf_key_група):
            opt_id   = str(person[cf_key_група])
            гр_label = cf_opts_група.get(opt_id, opt_id)
            if гр_label:
                prefix = f'Група прийняття рішень: {гр_label}'
                comment_val = f'{prefix}\n{comment_val}' if comment_val else prefix

        # ── 8. Create partner ──────────────────────────────────────────────────
        vals = {
            'name': name,
            'company_type': 'person',
            'parent_id': parent_id or False,
            'pipedrive_person_id': pd_id,
        }
        if email:
            vals['email'] = email
        if function_val:
            vals['function'] = function_val
        if comment_val:
            vals['comment'] = comment_val

        try:
            env.cr.execute('SAVEPOINT sp_person')
            partner = env['res.partner'].create(vals)

            for ph_entry in phone_entries:
                env['res.partner.phone'].create({
                    'partner_id': partner.id,
                    'phone': ph_entry['phone'],
                    'phone_type': ph_entry['phone_type'],
                    'is_primary': ph_entry['is_primary'],
                })
                # Update local cache
                existing_phones.setdefault(ph_entry['phone'], set()).add(partner.id)

            env.cr.execute('RELEASE SAVEPOINT sp_person')
            created += 1
            existing_person_ids.add(pd_id)

        except Exception as e:
            env.cr.execute('ROLLBACK TO SAVEPOINT sp_person')
            errors += 1
            if errors <= 10:
                print(f'  ПОМИЛКА (pd_id={pd_id}, name="{name}"): {e}')

        commit_counter += 1
        if commit_counter % COMMIT_EVERY == 0:
            env.cr.commit()
            done = created + skipped_existing + skipped_noname + merged_phone + errors
            print(
                f'  [стор {page_num}, ~{start + len(items)}/{total_pd}] '
                f'створено: {created}  пропущено: {skipped_existing + merged_phone + skipped_noname}  '
                f'помилок: {errors}'
            )

    # ── Pagination ─────────────────────────────────────────────────────────────
    pag = data.get('additional_data', {}).get('pagination', {})
    if not pag.get('more_items_in_collection'):
        break
    start = pag.get('next_start', start + PAGE_SIZE)
    time.sleep(SLEEP_S)

env.cr.commit()
print(f'\n=== Готово ===')
print(f'Створено нових:                {created}')
print(f'Вже були в Odoo (пропущено):   {skipped_existing}')
print(f'Дублі по телефону (пропущено): {merged_phone}')
print(f'Без імені (пропущено):         {skipped_noname}')
print(f'Помилки:                       {errors}')

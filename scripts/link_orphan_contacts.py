"""
Прив'язує контакти-"сироти" (без parent_id) до компаній через угоди Pipedrive.

Проблема: в Pipedrive контакт міг не мати прямого зв'язку з організацією,
але бути контактною особою угоди цієї організації. При імпорті такий контакт
опинився без parent_id і не з'являється в списку "Контакти" компанії.

Алгоритм:
  1. Читаємо deals.xlsx: person_id → org_id
  2. Контакти, що у всіх угодах мають ОДНУ org → прив'язуємо до неї
  3. Контакти з кількома орг → скіп (неоднозначно)

Запуск:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/link_orphan_contacts.py
"""
import pandas as pd
from collections import defaultdict

DEALS_PATH = '/var/odoo/2xqjwr7pzvj.cloudpepper.site/extra-addons/scripts/deals.xlsx'

print('=== Прив\'язка контактів до компаній ===')

# --- Будуємо маппінг person_id → set of org_ids із deals.xlsx ---
df = pd.read_excel(DEALS_PATH)
print(f'  {len(df)} угод в deals.xlsx')

person_to_orgs = defaultdict(set)  # pd_person_id → {pd_org_id, ...}
for _, row in df.iterrows():
    pd_pid = row.get('Ідентифікатор контактної особи')
    pd_oid = row.get('Ідентифікатор організації')
    if pd.isna(pd_pid) or pd.isna(pd_oid):
        continue
    person_to_orgs[int(pd_pid)].add(int(pd_oid))

# Лише person → ОДНА org (однозначні)
uniq_map = {pid: list(orgs)[0] for pid, orgs in person_to_orgs.items() if len(orgs) == 1}
multi_map = {pid: orgs for pid, orgs in person_to_orgs.items() if len(orgs) > 1}
print(f'  {len(uniq_map)} контактів з однозначною організацією')
print(f'  {len(multi_map)} контактів з кількома організаціями (скіп)')

# --- Одержуємо orphan persons з Odoo ---
env.cr.execute("""
    SELECT id, pipedrive_person_id
    FROM res_partner
    WHERE active=true AND is_company=false AND parent_id IS NULL
      AND pipedrive_person_id IS NOT NULL AND pipedrive_person_id > 0
""")
orphans = {r[1]: r[0] for r in env.cr.fetchall()}  # pd_person_id → partner_id
print(f'  {len(orphans)} orphan контактів в Odoo')

# --- Маппінг pd_org_id → res.partner.id ---
imd = env['ir.model.data'].search_read(
    [('module', '=', '__import__'), ('model', '=', 'res.partner'), ('name', 'like', 'pipedrive_org_')],
    ['name', 'res_id']
)
org_to_partner = {int(r['name'].replace('pipedrive_org_', '')): r['res_id'] for r in imd}

persons = env['res.partner'].search_read([('pipedrive_person_id', '>', 0)], ['pipedrive_person_id', 'id'])
person_odoo = {r['pipedrive_person_id']: r['id'] for r in persons}

# --- Виконуємо прив'язку ---
linked = 0
skipped_multi = 0
skipped_no_org = 0

fixes = []  # (partner_id, parent_id)
for pd_pid, odoo_pid in orphans.items():
    if pd_pid in multi_map:
        skipped_multi += 1
        continue
    if pd_pid not in uniq_map:
        skipped_no_org += 1
        continue
    pd_oid = uniq_map[pd_pid]
    odoo_cid = org_to_partner.get(pd_oid)
    if not odoo_cid:
        skipped_no_org += 1
        continue
    fixes.append((odoo_pid, odoo_cid))

print(f'  Для прив\'язки: {len(fixes)} контактів')
print(f'  Пропущено (кілька орг): {skipped_multi}')
print(f'  Пропущено (немає орг в Odoo): {skipped_no_org}')

# Батч UPDATE
if fixes:
    from collections import defaultdict
    by_parent = defaultdict(list)
    for pid, parent in fixes:
        by_parent[parent].append(pid)

    for parent_id, pids in by_parent.items():
        env.cr.execute(
            "UPDATE res_partner SET parent_id = %s WHERE id = ANY(%s) AND parent_id IS NULL",
            [parent_id, pids]
        )
        linked += env.cr.rowcount

    env.cr.commit()

print(f'\nПрив\'язано: {linked} контактів до компаній')
print('=== Готово ===')

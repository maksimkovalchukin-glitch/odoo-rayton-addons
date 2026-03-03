"""
Фаза 1 (локально): Підготовка даних для імпорту в Odoo.

Читає:
  - base_you_control/бази/База зі споживанням.xlsx  (680 компаній >= 40 МВт/міс)
  - base_you_control/База організацій повна(760 тис. орг) You Control Market.xlsx

Виводить:
  - output/new_leads.csv         — компанії зі споживанням, яких НЕМАЄ в Odoo
  - output/enrich_partners.csv   — збагачення для наявних контактів (телефон/email/директор)

Запуск: python scripts/prepare_bases.py
"""

import pandas as pd
import re
import os
import subprocess
import json
from pathlib import Path

BASE_DIR   = Path(__file__).parent.parent / 'base_you_control'
OUTPUT_DIR = Path(__file__).parent / 'output'
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Константи ─────────────────────────────────────────────────────────────────
FILE_CONSUMPTION = BASE_DIR / 'бази' / 'База зі споживанням.xlsx'
FILE_760K        = BASE_DIR / 'База організацій повна(760 тис. орг) You Control Market.xlsx'
CONSUMPTION_MIN_KWH = 30_000   # 30 МВт = 30 000 кВт*год/місяць

# Мобільні префікси UA (після 380)
UA_MOBILE_PREFIXES = {
    '50','63','66','67','68','73',
    '91','92','93','94','95','96','97','98','99',
}

# SSH для отримання ЄДРПОУ з Odoo
SSH_CMD = 'ssh -i ~/.ssh/cloudpepper_rayton root@70.34.250.223'
PG_DB   = '2xqjwr7pzvj.cloudpepper.site'


# ── Утиліти ──────────────────────────────────────────────────────────────────
def normalize_edrpou(val):
    """ЄДРПОУ → рядок 8 цифр із ведучими нулями."""
    if pd.isna(val):
        return None
    s = re.sub(r'\D', '', str(val))
    if len(s) < 5 or len(s) > 10:
        return None
    return s.zfill(8)


def extract_mobile_phones(raw_text):
    """
    Витягти тільки мобільні UA номери з довільного тексту.
    Повертає список нормалізованих рядків '+380XXXXXXXXX'.
    """
    if not raw_text or pd.isna(raw_text):
        return []
    text = str(raw_text)
    # Знаходимо всі послідовності цифр (і знак +)
    candidates = re.findall(r'[\+\d][\d\s\-\(\)]{8,14}', text)
    result = []
    for c in candidates:
        digits = re.sub(r'\D', '', c)
        # Нормалізуємо до 380XXXXXXXXX
        if digits.startswith('380') and len(digits) == 12:
            normalized = digits
        elif digits.startswith('80') and len(digits) == 11:
            normalized = '3' + digits
        elif digits.startswith('0') and len(digits) == 10:
            normalized = '38' + digits
        elif len(digits) == 9:
            normalized = '380' + digits
        else:
            continue
        # Перевіряємо мобільний префікс (2 символи після 380)
        prefix = normalized[3:5]
        if prefix in UA_MOBILE_PREFIXES:
            result.append('+' + normalized)
    # Дедуп
    seen = set()
    unique = []
    for p in result:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def best_mobile(phones_list):
    """Повертає перший мобільний номер зі списку або None."""
    return phones_list[0] if phones_list else None


# ── Крок 1: Завантажити ЄДРПОУ наявних компаній з Odoo ───────────────────────
print('=== Крок 1: Завантажуємо ЄДРПОУ з Odoo ===')

sql = "SELECT vat FROM res_partner WHERE vat IS NOT NULL AND vat != '' AND is_company=true AND active=true;"
result = subprocess.run(
    f'{SSH_CMD} "sudo -u postgres psql -d {PG_DB} -t -A -c \\"{sql}\\""',
    shell=True, capture_output=True, encoding='utf-8', errors='replace'
)

odoo_edirnpou = set()
stdout = result.stdout or ''
for line in stdout.strip().split('\n'):
    edr = normalize_edrpou(line.strip())
    if edr:
        odoo_edirnpou.add(edr)

print(f'  Знайдено в Odoo: {len(odoo_edirnpou):,} компаній з ЄДРПОУ')


# ── Крок 2: Читаємо базу споживання ──────────────────────────────────────────
print(f'\n=== Крок 2: Читаємо базу споживання ({FILE_CONSUMPTION.name}) ===')

df_cons = pd.read_excel(FILE_CONSUMPTION, dtype={'ЄДРПОУ': str})

# Авто-визначення колонок (назви можуть відрізнятись)
cols = list(df_cons.columns)
print(f'  Колонки: {cols}')

# Знаходимо колонки за позицією (структура стабільна)
col_edrpou  = cols[0]   # A: ЄДРПОУ
col_name    = cols[1]   # B: Назва
col_kwh     = cols[2]   # C: Споживання кВт*год/міс
col_contact = cols[3]   # D: ОПР ПІБ
col_phone   = cols[4]   # E: ОПР тел.
col_director= cols[6]   # G: Керівник (якщо є)
col_sphere  = cols[7]   # H: Сфера діяльності
col_address = cols[8]   # I: Адреса

df_cons['_edrpou'] = df_cons[col_edrpou].apply(normalize_edrpou)
df_cons['_kwh']    = pd.to_numeric(df_cons[col_kwh], errors='coerce').fillna(0)
df_cons['_mwh']    = (df_cons['_kwh'] / 1000).round(1)

# Фільтр >= 30 МВт
df_30 = df_cons[df_cons['_kwh'] >= CONSUMPTION_MIN_KWH].copy()
print(f'  Всього рядків: {len(df_cons):,}')
print(f'  >= 30 МВт/міс: {len(df_30):,}')

# Нормалізуємо телефони з бази споживання
df_30['_phone_clean'] = df_30[col_phone].apply(
    lambda x: best_mobile(extract_mobile_phones(x))
)


# ── Крок 3: Читаємо 760к базу (тільки потрібні колонки) ──────────────────────
print(f'\n=== Крок 3: Читаємо 760к базу ===')
print('  (це займе 2-3 хвилини...)')

# Колонки за індексом (перевірено на реальних даних):
# 0: ЄДРПОУ (поле "ПІБ" в хедері — для компаній містить ЄДРПОУ)
# 8: Телефон (мобільний), 9: Email,
# 11: Доп. контакт (ще один телефон), 20: Область, 22: Місто
USECOLS = [0, 8, 9, 11, 20, 22]

df_760 = pd.read_excel(
    FILE_760K,
    usecols=USECOLS,
    dtype={0: str},  # ЄДРПОУ як рядок
    engine='openpyxl',
)
df_760.columns = ['edrpou_raw', 'phone_raw', 'email_raw', 'extra_contact', 'region', 'city']

df_760['edrpou'] = df_760['edrpou_raw'].apply(normalize_edrpou)
df_760 = df_760[df_760['edrpou'].notna()].copy()

print(f'  Завантажено рядків: {len(df_760):,}')

# Нормалізуємо телефони: основний + додатковий контакт
def get_best_phone(row):
    phones = extract_mobile_phones(row['phone_raw'])
    if not phones:
        phones = extract_mobile_phones(row['extra_contact'])
    return best_mobile(phones)

df_760['phone_clean'] = df_760.apply(get_best_phone, axis=1)
df_760['email_clean'] = df_760['email_raw'].apply(
    lambda x: str(x).strip().lower() if pd.notna(x) and '@' in str(x) else None
)

# Дедуп: один запис на ЄДРПОУ (пріоритет: є телефон, є email)
df_760 = df_760.sort_values(
    ['phone_clean', 'email_clean'],
    ascending=[False, False],
    na_position='last'
)
df_760_dedup = df_760.drop_duplicates(subset='edrpou', keep='first')
print(f'  Унікальних ЄДРПОУ: {len(df_760_dedup):,}')

# Словник для швидкого пошуку
enrichment_map = df_760_dedup.set_index('edrpou')[
    ['phone_clean', 'email_clean', 'region', 'city']
].to_dict('index')


# ── Крок 4: Розділяємо на "нові ліди" та "збагачення" ───────────────────────
print('\n=== Крок 4: Розподіл компаній ===')

new_leads   = []
to_enrich   = []

for _, row in df_30.iterrows():
    edr  = row['_edrpou']
    if not edr:
        continue

    enr = enrichment_map.get(edr, {})

    # Кращий телефон: з бази споживання або з 760к
    phone = row['_phone_clean'] or enr.get('phone_clean')

    record = {
        'edrpou':     edr,
        'name':       str(row[col_name]).strip(),
        'mwh_month':  row['_mwh'],
        'phone':      phone,
        'email':      enr.get('email_clean'),
        'director':   row.get(col_director),
        'sphere':     row.get(col_sphere),
        'region':     enr.get('region'),
        'city':       enr.get('city'),
        'address':    row.get(col_address),
        'contact_person': row.get(col_contact),
    }

    if edr in odoo_edirnpou:
        to_enrich.append(record)
    else:
        new_leads.append(record)

print(f'  Нових лідів (немає в Odoo): {len(new_leads):,}')
print(f'  Для збагачення (вже в Odoo): {len(to_enrich):,}')


# ── Крок 5: Збагачення ВСІХ Odoo-компаній з 760к ─────────────────────────────
print('\n=== Крок 5: Збагачення всіх Odoo-контактів з 760к ===')

all_enrich = []
for edr in odoo_edirnpou:
    enr = enrichment_map.get(edr)
    if enr and (enr.get('phone_clean') or enr.get('email_clean')):
        all_enrich.append({
            'edrpou':   edr,
            'phone':    enr.get('phone_clean'),
            'email':    enr.get('email_clean'),
            'region':   enr.get('region'),
            'city':     enr.get('city'),
        })

print(f'  Odoo-контактів з даними в 760к: {len(all_enrich):,}')


# ── Крок 6: Зберігаємо CSV ───────────────────────────────────────────────────
print('\n=== Крок 6: Зберігаємо CSV ===')

df_new = pd.DataFrame(new_leads)
df_new.to_csv(OUTPUT_DIR / 'new_leads.csv', index=False, encoding='utf-8-sig')
print(f'  new_leads.csv -> {len(df_new)} рядків')

df_enrich = pd.DataFrame(all_enrich)
df_enrich.to_csv(OUTPUT_DIR / 'enrich_partners.csv', index=False, encoding='utf-8-sig')
print(f'  enrich_partners.csv -> {len(df_enrich)} рядків')

print('\nГотово! Запустіть тепер import_bases_to_odoo.py на сервері.')
print(f'   Файли: {OUTPUT_DIR}')

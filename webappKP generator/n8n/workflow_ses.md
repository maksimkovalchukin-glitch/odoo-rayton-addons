# n8n Workflow — Генератор КП СЕС

## Схема вузлів

```
[Webhook]
   ↓
[SheetsData] + [SheetsRates]
   ↓
[Code: Calculate]        ← ses_calculate.js
   ↓
[Code: Charts]           ← ses_charts.js  (генерація + QuickChart URLs)
   ↓
[HTTP: Download YearChart PNG]   ← GET quickchart.io/chart?...
[HTTP: Download DayChart PNG]    ← GET quickchart.io/chart?...
   ↓
[Drive: Copy Template]
   ↓
[Code: Build Docs Requests]      ← replaceAllText + insertImage
   ↓
[HTTP: Docs batchUpdate]
   ↓
[HTTP: Export PDF]
   ↓
[Drive: Save PDF]
   ↓
[Telegram: Send Document]
```

---

## Вузол 1 — Webhook

| Параметр | Значення |
|----------|----------|
| Method   | POST |
| Path     | `/ses-kp` або вибрати автоматично |
| Response | Immediately (200 OK) |

**Webhook URL** прописати в `ses2/ses.js`:
```js
const WEBHOOK_URL = "https://n8n.rayton.net/webhook/ВАШ_PATH";
```

---

## Вузол 2 — SheetsData (Google Sheets: Read)

| Параметр | Значення |
|----------|----------|
| Operation | Get Many Rows |
| Spreadsheet | Генератор КП СЕС Основний |
| Sheet | Довідкові дані |
| Range | A1:I200 |
| Options → First Row as Column Names | ✅ Увімкнути |

> Перший рядок аркуша повинен містити заголовки колонок (A..I).
> Важливо щоб колонки позиціонувались саме так:
> **A=Категорія, B=Назва, C=Одиниця, D=К-сть, E=Ціна, F=Закупівля, G=Коефіцієнт, H=_, I=Продаж**

---

## Вузол 3 — SheetsRates (Google Sheets: Read)

| Параметр | Значення |
|----------|----------|
| Operation | Get Many Rows |
| Sheet | Довідкові дані |
| Range | O1:O2 |
| Options → First Row as Column Names | ❌ Вимкнути |

> O1 = курс EUR до UAH (наприклад 43.5)
> O2 = курс USD до UAH (наприклад 41.2)

---

## Вузол 4 — Code: Calculate

**Mode:** Run Once for All Items
**Language:** JavaScript

Вставити весь вміст файлу `ses_calculate.js`.

**Налаштування входів (Input Data):**
- У секції "Input" прив'язати до попередніх вузлів:
  - `$('Webhook')` — вузол Webhook
  - `$('SheetsData')` — вузол SheetsData
  - `$('SheetsRates')` — вузол SheetsRates

---

## Вузол 5 — Drive: Copy Template

| Параметр | Значення |
|----------|----------|
| Operation | Copy |
| File ID | `{{ $json.templateDocId }}` |
| Name | `{{ $json.doc_copy_name }}` |
| Parent Folder | `{{ $json.driveFolderId }}` |

**Вивід**: зберігає `id` та `webViewLink` нової копії документа.

---

## Вузол 6 — Code: Build Docs Requests

Після Drive Copy, формуємо масив `requests` для Docs API (batchUpdate):

```javascript
const calcData = $('Code: Calculate').first().json;
const docId    = $('Drive: Copy Template').first().json.id;
const vars     = calcData.template_vars;

// Формуємо replaceAllText запити
const requests = Object.entries(vars).map(([tag, value]) => ({
  replaceAllText: {
    containsText: { text: tag, matchCase: true },
    replaceText:  String(value ?? ''),
  }
}));

return [{ json: { docId, requests } }];
```

---

## Вузол 7 — HTTP Request: Docs batchUpdate

| Параметр | Значення |
|----------|----------|
| Method | POST |
| URL | `https://docs.googleapis.com/v1/documents/{{ $json.docId }}:batchUpdate` |
| Auth | Google OAuth2 (Docs API scope) |
| Body (JSON) | `{ "requests": {{ $json.requests }} }` |

---

## Вузол 8 — HTTP Request: Export PDF

| Параметр | Значення |
|----------|----------|
| Method | GET |
| URL | `https://docs.google.com/document/d/{{ $json.docId }}/export?format=pdf&tab=0` |
| Auth | Google OAuth2 |
| Response | Binary (PDF) |
| Binary Property | `data` |

---

## Вузол 9 — Drive: Save PDF

| Параметр | Значення |
|----------|----------|
| Operation | Upload |
| Parent Folder | `{{ $('Code: Calculate').first().json.driveFolderId }}` |
| File Name | `{{ $('Code: Calculate').first().json.file_name }}` |
| Binary Property | `data` |

---

## Вузол 10 — Telegram: Send Document

| Параметр | Значення |
|----------|----------|
| Operation | Send Document |
| Chat ID | `{{ $('Code: Calculate').first().json.chat_id }}` |
| Binary Property | `data` |
| Caption | `КП для {{ $('Code: Calculate').first().json.project_name }} ({{ $('Code: Calculate').first().json.power_label }}) — готово! ✅` |

---

## Важливі зауваження

### Структура довідника (колонка G — Коефіцієнт)
- Має бути числом (наприклад `1.5`, `2.3`)
- НЕ формула, просто значення
- При ітерації n8n **не записує** нічого назад у таблицю (read-only)

### Паралельна робота менеджерів
- Кожен запит до вебхука = окремий n8n execution
- Ніякого спільного стану — проблеми з паралельністю відсутні ✅

### Режим "без ПДВ"
- При `price_vat = "without"` — ЄП податок НЕ додається до підсумку
- Цільова ціна за кВт береться без коригування на ЄП

### Якщо позиція не знайдена в довіднику
- Рядок тихо пропускається (`addLine` повертає 0)
- У фінальній таблиці позиція залишається порожньою
- Перевіряйте відповідність назв у webapp та в аркуші "Довідкові дані"

### Налаштування шаблонів Google Docs
Перевірити ID шаблонів у `ses_calculate.js` (рядки `TEMPLATE_*_ID`):
```
TEMPLATE_NO_CREDIT_ID          = '1Ytn9wssFM-...'
TEMPLATE_NO_CREDIT_NO_IMG_ID   = '1LGbc5siAxP6...'
```

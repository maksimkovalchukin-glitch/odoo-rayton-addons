/* ================================================================
   n8n Code Node — Формування batchUpdate запиту для Google Docs
   (replaceAllText + inline image insertion через Drive URL)

   Входи:
     $('Code: Charts')              — дані розрахунку + URLs графіків
     $('Drive: Copy Template')      — id скопійованого документа
     $('HTTP: Download YearChart')  — бінарний PNG річного графіка
     $('HTTP: Download DayChart')   — бінарний PNG денного графіка

   ПРИМІТКА: Google Docs API не підтримує вставку бінарних зображень
   напряму через batchUpdate — потрібен публічний URL або Drive file ID.
   Тому:
     1. Завантажуємо PNG через HTTP у Drive (тимчасово, публічно)
     2. Отримуємо URL
     3. Вставляємо через insertInlineImage з imageUri
================================================================ */

const calc  = $('Code: Charts').first().json;
const docId = $('Drive: Copy Template').first().json.id;
const vars  = calc.template_vars;

// ─── 1. replaceAllText для всіх {{placeholder}} ───
const replaceRequests = Object.entries(vars).map(([tag, value]) => ({
  replaceAllText: {
    containsText: { text: tag, matchCase: true },
    replaceText:  String(value ?? ''),
  }
}));

// ─── 2. Інформація про зображення ───
// Зображення вставляємо через Drive public link або через окремий підхід.
// Якщо PNG завантажено у Drive через вузол "Drive: Upload YearChart":
const yearChartFileId = $('Drive: Upload YearChart')?.first()?.json?.id || null;
const dayChartFileId  = $('Drive: Upload DayChart')?.first()?.json?.id  || null;

// Google Drive URL для публічного доступу (файл має бути shared: "anyone with link")
const yearChartUrl = yearChartFileId
  ? `https://drive.google.com/uc?id=${yearChartFileId}`
  : calc.year_chart_url;  // fallback: QuickChart URL напряму

const dayChartUrl = dayChartFileId
  ? `https://drive.google.com/uc?id=${dayChartFileId}`
  : calc.day_chart_url;

// ─── 3. insertInlineImage через replaceAllText + маркер ───
// В шаблоні Google Doc маємо маркери {{year_chart}} і {{day_chart}}
// які є текстом у рядку. Спочатку видаляємо текст маркера,
// потім вставляємо зображення за індексом.
//
// ПРОСТІШИЙ ПІДХІД: замінюємо {{year_chart}} на пустий рядок через replaceAllText,
// а зображення вставляємо окремим запитом insertInlineImage з об'єктом location.
//
// АБО: використовуємо replaceAllText з URL-посиланням на зображення
// (Docs API дозволяє insertInlineImage з imageUri через batchUpdate).

// Додаємо запити на вставку зображень (якщо маркери є в шаблоні)
const imageRequests = [];

// Спочатку замінюємо маркери на пробіл (щоб знайти позицію)
// Потім вставляємо зображення — це двокроковий процес.
// Для спрощення: якщо QuickChart URL публічний — можна вставити через URL напряму.

// Видаляємо текстові маркери (вони вже оброблені як '' в replaceRequests вище)
// Зображення буде вставлено через окремий HTTP запит до Docs API:

return [{
  json: {
    docId,
    // Всі replace запити для тексту
    requests: replaceRequests,

    // Окремо — дані для вставки зображень (обробляються наступним вузлом)
    year_chart_url: yearChartUrl,
    day_chart_url:  dayChartUrl,

    // Передаємо решту даних далі
    chat_id:    calc.chat_id,
    file_name:  calc.file_name,
    project_name: calc.project_name,
    power_label:  calc.power_label,
    total_display: calc.total_display,
    currency_sign: calc.currency_sign,
    drive_folder_id: calc.driveFolderId,
  }
}];

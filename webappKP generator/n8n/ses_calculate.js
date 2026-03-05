/* ================================================================
   n8n Code Node — Розрахунок КП СЕС v1.0

   ВХОДИ (Input nodes):
     "Webhook"      — payload з Telegram Mini App (ses2)
     "SheetsData"   — рядки аркуша "Довідкові дані" (діапазон A1:I200)
                      кожен item.json — об'єкт із полями колонок
     "SheetsRates"  — діапазон O1:O2 того ж аркуша (2 рядки × 1 колонка)

   ВИХІД:
     Один об'єкт JSON з усіма даними для наступних вузлів:
       — Google Drive: Copy template
       — Google Docs:  Fill placeholders
       — Telegram:     Send PDF

   СТРУКТУРА "Довідкові дані" (колонки A-I):
     A = Категорія   (Фотоелектричні модулі / Мережеві інвертори / ...)
     B = Назва       (назва позиції)
     C = Одиниця     (шт., компл., кВт...)
     D = К-сть       (заповнюється скриптом, в n8n ігноруємо)
     E = Ціна USD    (базова ціна без націнки)
     F = Закупівля   (формула E*D — ігноруємо)
     G = Коефіцієнт  (націнка, mutable при ітерації)
     H = —           (ігноруємо)
     I = Продаж      (формула E*G*D — ігноруємо)

   Рядки O1/O2:
     O1 = UAH за EUR (наприклад 43.50)
     O2 = UAH за USD (наприклад 41.20)
================================================================ */

// ────────────────────────────────────────────────────────────────
// 1. ВХІДНІ ДАНІ
// ────────────────────────────────────────────────────────────────

const _wh = $('Webhook').first().json;
const p = _wh.body ?? _wh; // webhook v2 вкладає body в json.body

// n8n Google Sheets v4 (firstRowIsColumnNames: false) використовує рядок 1 як заголовки
// і додає поле row_number → ключі: row_number, col_1(A), col_2(B), col_3(C),
// "К-сть"(D), col_5(E=Ціна USD), col_6(F), col_7(G=Коефіцієнт), ...
// Остання колонка O: її ключ = значення O1 (курс EUR), значення для рядка = курс USD
const rawItems = $('SheetsData').all();

const parseFlt = v => {
  if (v === null || v === undefined || v === '') return 0;
  return parseFloat(String(v).replace(/\s/g, '').replace(',', '.')) || 0;
};

// Курси валют: col O header = EUR rate (key name), col O row1 value = USD rate
const _firstJson  = rawItems[0]?.json || {};
const _allKeys    = Object.keys(_firstJson);
const _rateColKey = _allKeys[_allKeys.length - 1];        // ключ колонки O
const rateEUR     = parseFlt(_rateColKey) || 43.5;        // значення O1 = EUR курс
const rateUSD     = parseFlt(_firstJson[_rateColKey]) || 41.2;  // значення O2 = USD курс

// Нормалізація кирилиця→латиниця для візуальних омогліфів у назвах обладнання
// (наприклад, кирилична Т = U+0422 та латинська T = U+0054 виглядають однаково,
//  але це різні символи → порівняння провалюється без нормалізації)
function normName(s) {
  return s
    .replace(/А/g,'A').replace(/а/g,'a')
    .replace(/В/g,'B').replace(/в/g,'b')
    .replace(/Е/g,'E').replace(/е/g,'e')
    .replace(/К/g,'K').replace(/к/g,'k')
    .replace(/М/g,'M').replace(/м/g,'m')
    .replace(/Н/g,'H').replace(/н/g,'h')
    .replace(/О/g,'O').replace(/о/g,'o')
    .replace(/Р/g,'P').replace(/р/g,'p')
    .replace(/С/g,'C').replace(/с/g,'c')
    .replace(/Т/g,'T').replace(/т/g,'t')
    .replace(/У/g,'Y').replace(/у/g,'y')
    .replace(/Х/g,'X').replace(/х/g,'x');
}

// Будуємо зручний масив рядків довідника (тільки ті що мають категорію + ціну)
// Доступ по стабільних ключах n8n: col_1=A, col_2=B, col_3=C, col_5=E, col_7=G
// Назви (col_2) нормалізуємо — у таблиці можуть бути кириличні омогліфи в назвах брендів
const refData = rawItems
  .map(item => ({
    category: String(item.json['col_1'] || '').trim(),           // A = Категорія (завжди кирилиця)
    name:     normName(String(item.json['col_2'] || '').replace(/\n/g, ' ').trim()), // B = Назва (нормалізована, \n→пробіл)
    unit:     String(item.json['col_3'] || '').trim(),           // C = Одиниця
    price:    parseFlt(item.json['col_5']),                      // E = Ціна USD
    markup:   parseFlt(item.json['col_7']) || 1,                 // G = Коефіцієнт
  }))
  .filter(r => r.category && r.name && r.price > 0);

// currencyRate: скільки EUR за 1 USD (для конвертації)
// Внутрішні ціни в довіднику = USD.
// Якщо вибрано USD — currencyRate = 1 (не конвертуємо).
// Якщо вибрано EUR — currencyRate = usdRate/eurRate ≈ 0.946 (USD→EUR).
const currency     = p.currency || 'USD';         // "USD" | "EUR"
const currencyRate = currency === 'EUR' ? rateUSD / rateEUR : 1;
const currSign     = currency === 'EUR' ? '€' : '$';

const vatMode = p.price_vat || 'with'; // "with" | "without"

// ────────────────────────────────────────────────────────────────
// 2. ПАРАМЕТРИ СТАНЦІЇ (вже розраховані у webapp)
// ────────────────────────────────────────────────────────────────

const dcKW      = parseFlt(p.real_dc);      // DC потужність, кВт
const acKW      = parseFlt(p.real_ac);      // AC потужність, кВт
const panelQty  = parseInt(p.panel_qty) || 0;
const panelWatt = parseInt(p.module_watt) || 620;
const sesType   = p.ses_type || 'Дахова';   // "Дахова" | "Наземна"
const matType   = (p.material_type || 'DC та AC').toLowerCase();
const isDC      = matType.includes('dc');
const isAC      = matType.includes('ac');

// Ітнвертори (до 3 типів)
const inverters = [];
for (let i = 1; i <= 3; i++) {
  const model = p[`inverter_${i}_model`];
  const qty   = parseInt(p[`inverter_${i}_qty`]) || 0;
  if (model && qty > 0) inverters.push({ model, qty });
}

// Типи кріплення [{type, qty}]
const mountTypes = Array.isArray(p.mount_types) ? p.mount_types : [];

// ────────────────────────────────────────────────────────────────
// 3. КОНСТАНТИ КАТЕГОРІЙ ТА ЛІМІТІВ НАЦІНОК
// ────────────────────────────────────────────────────────────────

// Ці категорії мають фіксовану націнку (не змінюємо при ітерації)
const FIXED_CATS = new Set([
  'фотоелектричні модулі',
  'мережеві інвертори',
  'пристрій моніторингу',
  'система регулювання потужності',
]);

// Ліміти [min, max] для змінних категорій
const MARKUP_LIMITS = {
  'система кріплення':              [1.0, 7.1875],
  'матеріали dc до 100 квт':        [1.0, 6.75],
  'матеріали ac до 100 квт':        [1.0, 6.75],
  'матеріали dc більше 100 квт':    [1.0, 6.75],
  'матеріали ac більше 100 квт':    [1.0, 6.75],
  'монтаж':   [1.0, 3.0188],
  'техніка':  [1.0, 3.0188],
  'доставка': [1.0, 3.0188],
};

// ────────────────────────────────────────────────────────────────
// 4. MUTABLE НАЦІНКИ (копія з довідника, змінюємо при ітерації)
// ────────────────────────────────────────────────────────────────

// Зберігаємо як Map: "категорія|назва" → markup
const markupMap = new Map();
refData.forEach(r => {
  // r.name вже нормалізована (normName при побудові refData)
  markupMap.set(`${r.category.toLowerCase()}|${r.name.toLowerCase()}`, r.markup);
});

function getMarkup(category, name) {
  return markupMap.get(`${category.toLowerCase()}|${normName(name).toLowerCase()}`) || 1;
}

function setMarkup(category, name, val) {
  markupMap.set(`${category.toLowerCase()}|${normName(name).toLowerCase()}`, val);
}

function findRow(category, name) {
  const normN = normName(name).toLowerCase();
  return refData.find(r =>
    r.category.toLowerCase() === category.toLowerCase() &&
    r.name.toLowerCase() === normN
  ) || null;
}

// ────────────────────────────────────────────────────────────────
// 5. ЛЕЙБЛИ ДЛЯ ПОСЛУГ (залежать від потужності і типу СЕС)
// ────────────────────────────────────────────────────────────────

function getMontageLabel(kw) {
  if (kw <= 80)   return '50-80 кВт';
  if (kw <= 100)  return '80-100 кВт';
  if (kw <= 250)  return '100-250 кВт';
  if (kw <= 500)  return '250-500 кВт';
  if (kw <= 1000) return '500-1000 кВт';
  return '1000 та більше';
}

function getTechLabel(type, kw) {
  if (type === 'Наземна') return 'наземка за кВт';
  if (kw <= 100)  return 'дах 50-100 кВт';
  if (kw <= 150)  return 'дах 80-150 кВт';
  if (kw <= 300)  return 'дах 150-300 кВт';
  if (kw <= 500)  return 'дах 300-500 кВт';
  if (kw <= 1000) return 'дах 500-1000 кВт';
  if (kw <= 1500) return 'дах 1000-1500 кВт';
  if (kw <= 2000) return 'дах 1500-2000 кВт';
  return 'дах більше 2000 кВт';
}

function getDeliveryLabel(kw) {
  if (kw <= 100)  return '50-100 кВт';
  if (kw <= 250)  return '100-250 кВт';
  if (kw <= 500)  return '250-500 кВт';
  if (kw <= 1000) return '500-1000 кВт';
  return '1000 та більше';
}

const montageLabel  = getMontageLabel(dcKW);
const techLabel     = getTechLabel(sesType, dcKW);
const deliveryLabel = getDeliveryLabel(dcKW);
const techQty       = sesType === 'Наземна' ? dcKW : 1;

// Категорії матеріалів DC/AC (залежать від DC потужності)
const rangeDC = dcKW <= 100 ? 'Матеріали DC до 100 кВт'   : 'Матеріали DC більше 100 кВт';
const rangeAC = dcKW <= 100 ? 'Матеріали AC до 100 кВт'   : 'Матеріали AC більше 100 кВт';

// ────────────────────────────────────────────────────────────────
// 6. ФУНКЦІЯ РОЗРАХУНКУ ЗАГАЛЬНОЇ ВАРТОСТІ
//    Повертає все в USD (currencyRate не застосовується тут).
//    lineItems містить ціни в USD — конвертуємо тільки для відображення.
// ────────────────────────────────────────────────────────────────

function calculateAll() {
  let sumSale     = 0;  // сума продажу (USD) — з націнками
  let sumPurchase = 0;  // сума закупівлі (USD) — без націнок
  const lineItems = [];  // для шаблону КП

  // ─── Допоміжна функція додавання позиції ───
  function addLine(category, name, qty, unitOverride, labelOverride) {
    const row = findRow(category, name);
    if (!row || qty <= 0 || row.price === 0) return 0;
    const mu       = getMarkup(category, name);
    const saleUnit = row.price * mu;
    const sale     = saleUnit * qty;
    const purchase = row.price * qty;
    sumSale     += sale;
    sumPurchase += purchase;
    lineItems.push({
      category,
      name:      labelOverride || name,
      unit:      unitOverride || row.unit || 'шт.',
      qty,
      unitPriceUSD: +saleUnit.toFixed(4),
      totalUSD:     +sale.toFixed(4),
    });
    return sale;
  }

  // ─── Панелі ───
  // module_type = "Фотоелектричні модулі Тrina 575W" — прибираємо категорію для відображення в PDF
  const _panelDisplayName = (p.module_type || '').replace(/^Фотоелектричні модулі\s*/i, '').replace(/\n/g, ' ').trim();
  addLine('Фотоелектричні модулі', p.module_type, panelQty, 'шт.',
    `Фотогальванічний модуль ${_panelDisplayName}`);

  // ─── Інвертори ───
  inverters.forEach(inv =>
    addLine('Мережеві інвертори', inv.model, inv.qty, 'шт.', `Інвертор ${inv.model}`)
  );

  // ─── Моніторинг ───
  addLine('Пристрій моніторингу', p.monitoring_device, 1, 'шт.',
    `Моніторинг ${p.monitoring_device}`);

  // ─── Система регулювання потужності ───
  addLine('Система регулювання потужності', p.power_regulation, 1, 'компл.',
    `Регулювання потужності ${p.power_regulation}`);

  // ─── Кріплення (зважене середнє по типах) ───
  let mountTotalQty    = 0;
  let mountSaleSum     = 0;
  let mountPurchaseSum = 0;

  mountTypes.forEach(mt => {
    const row = findRow('Система кріплення', mt.type);
    if (!row || mt.qty <= 0) return;
    const mu = getMarkup('Система кріплення', mt.type);
    mountTotalQty    += mt.qty;
    mountSaleSum     += row.price * mu * mt.qty;
    mountPurchaseSum += row.price * mt.qty;
  });

  if (mountTotalQty > 0) {
    sumSale     += mountSaleSum;
    sumPurchase += mountPurchaseSum;
    lineItems.push({
      category: 'Система кріплення',
      name:     'Кріплення фотомодулів',
      unit:     'компл.',
      qty:      1,
      unitPriceUSD: +mountSaleSum.toFixed(4),
      totalUSD:     +mountSaleSum.toFixed(4),
    });
  }

  // ─── Матеріали DC / AC (розподілені по типах кріплення) ───
  // Ціна матеріалів у довіднику = USD/кВт DC для даного типу кріплення.
  // Обсяг (кВт) = кількість панелей цього типу * watt / 1000.

  function getDistributedMaterial(range) {
    let totalSale = 0, totalPurchase = 0;
    mountTypes.forEach(mt => {
      const allocKW = (mt.qty * panelWatt) / 1000;  // DC потужність цього сегменту
      const matches = refData.filter(r =>
        r.category.toLowerCase() === range.toLowerCase() &&
        r.name.toLowerCase()     === mt.type.toLowerCase()
      );
      matches.forEach(row => {
        const mu = getMarkup(row.category, row.name);
        totalSale     += row.price * mu * allocKW;
        totalPurchase += row.price * allocKW;
      });
    });
    return { sale: totalSale, purchase: totalPurchase };
  }

  // Ручний додаток (рядок "Дод. матеріали до AC та DC")
  const extraRow = refData.find(r => r.category === 'Дод. матеріали до AC та DC');
  const manualExtra = extraRow ? extraRow.price * (extraRow.markup || 1) : 0;

  const dcMat = isDC ? getDistributedMaterial(rangeDC) : { sale: 0, purchase: 0 };
  const acMat = isAC ? getDistributedMaterial(rangeAC) : { sale: 0, purchase: 0 };

  const matTotalSale     = dcMat.sale + acMat.sale + manualExtra;
  const matTotalPurchase = dcMat.purchase + acMat.purchase + manualExtra;

  if (matTotalSale > 0) {
    let matLabel = 'PV кабель, конектори MC4, автоматика струмового захисту, монтажний комплект (короб, лоток, гофротруби, трансформатори, ізоляційні матеріали і т.д)';
    if (isDC && isAC) matLabel += ' + AC';
    else if (isAC)   matLabel += ' AC';

    sumSale     += matTotalSale;
    sumPurchase += matTotalPurchase;
    lineItems.push({
      category: 'Матеріали',
      name:     matLabel,
      unit:     'компл.',
      qty:      1,
      unitPriceUSD: +matTotalSale.toFixed(4),
      totalUSD:     +matTotalSale.toFixed(4),
    });
  }

  // ─── Послуги (монтаж + техніка + доставка) ───
  let servicesSale = 0, servicesPurchase = 0;

  function addService(category, label, qty) {
    const row = findRow(category, label);
    if (!row) return;
    const mu  = getMarkup(category, label);
    const s   = row.price * mu * qty;
    const pur = row.price * qty;
    servicesSale     += s;
    servicesPurchase += pur;
  }

  addService('Монтаж',   montageLabel,  dcKW);
  addService('Техніка',  techLabel,     techQty);
  addService('Доставка', deliveryLabel, 1);

  if (servicesSale > 0) {
    sumSale     += servicesSale;
    sumPurchase += servicesPurchase;
  }

  return {
    sumSale,     // USD, з націнками, без податку
    sumPurchase, // USD, без націнок
    lineItems,
    servicesSale,
  };
}

// ────────────────────────────────────────────────────────────────
// 7. ІТЕРАЦІЙНЕ КОРИГУВАННЯ НАЦІНОК
//    Мета: totalSale / dc_kw ≈ targetPricePerKW (в обраній валюті)
// ────────────────────────────────────────────────────────────────

// Цільова ціна в USD (внутрішня)
let targetPricePerKWinUSD = parseFlt(p.price_per_kw) || 380;
if (currency === 'EUR') {
  // Менеджер вводив в EUR → конвертуємо в USD для порівняння
  targetPricePerKWinUSD = targetPricePerKWinUSD / currencyRate;
}

if (dcKW > 0) {
  for (let iter = 0; iter < 30; iter++) {
    const { sumSale, sumPurchase } = calculateAll();
    if (sumSale === 0) break;

    // Оцінюємо finalTotal так само як секція 8:
    // finalTotal = (sumSale + taxValue_last) * currencyRate
    // taxValue_last — значення після 2-ї ітерації ЄП (не кумулятивне)
    let _ss = sumSale, _sp = sumPurchase, _tv = 0;
    if (vatMode === 'with') {
      for (let i = 0; i < 2; i++) {
        _tv = ((_ss - _sp) / 1.025 * 0.24) + (_ss * 0.013);
        _ss += _tv; _sp += _tv;
      }
    }
    // estimatedFinalUSD = sumSale + taxValue_last (без currencyRate, оскільки target вже в USD)
    const estimatedFinalUSD    = sumSale + (vatMode === 'with' ? _tv : 0);
    const actualPricePerKWinUSD = estimatedFinalUSD / dcKW;
    const scaleFactor = targetPricePerKWinUSD / actualPricePerKWinUSD;

    // Якщо достатньо точно — виходимо (0.00005% → похибка <$1 навіть для 5 МВт)
    if (Math.abs(scaleFactor - 1) < 0.000001) break;

    // Масштабуємо некеровані категорії
    markupMap.forEach((markup, key) => {
      const [category] = key.split('|');
      if (FIXED_CATS.has(category)) return;

      const [minM, maxM] = MARKUP_LIMITS[category] || [1, 5];
      const newMarkup    = Math.max(minM, Math.min(markup * scaleFactor, maxM));
      markupMap.set(key, +newMarkup.toFixed(6));
    });
  }
}

// ────────────────────────────────────────────────────────────────
// 8. ФІНАЛЬНИЙ РОЗРАХУНОК
// ────────────────────────────────────────────────────────────────

const { sumSale, sumPurchase, lineItems, servicesSale } = calculateAll();

// ─── Розрахунок ЄП (єдиний податок, 2 ітерації) ───
// Формула: ((продаж - закупівля) / 1.025 * 0.24) + (продаж * 0.013)
// — це ЄП 3-ї групи (24% на прибуток з урахуванням коефіцієнта) + 1.3% від обороту (воєнний збір)
let spSumSale     = sumSale;
let spSumPurchase = sumPurchase;
let taxValue      = 0;

for (let i = 0; i < 2; i++) {
  taxValue       = ((spSumSale - spSumPurchase) / 1.025 * 0.24) + (spSumSale * 0.013);
  spSumSale     += taxValue;
  spSumPurchase += taxValue;
}
taxValue = +taxValue.toFixed(2);

// Конвертуємо податок у вибрану валюту
const taxValueConverted = +(taxValue * currencyRate).toFixed(2);

// Загальна сума в обраній валюті (БЕЗ ЄП — для "без ПДВ" режиму)
const totalBeforeTaxConverted = +(sumSale * currencyRate).toFixed(2);

// Загальна сума З ЄП
const totalWithTaxConverted = +(totalBeforeTaxConverted + taxValueConverted).toFixed(2);

// Остаточна сума залежно від режиму ПДВ
const finalTotal = vatMode === 'with' ? totalWithTaxConverted : totalBeforeTaxConverted;

// Рядки позицій з конвертованими цінами
const lineItemsConverted = lineItems.map((item, idx) => ({
  ...item,
  unitPrice: +(item.unitPriceUSD * currencyRate).toFixed(2),
  total:     +(item.totalUSD     * currencyRate).toFixed(2),
}));

// ─── Додаємо ЄП до останньої позиції обладнання (як в оригінальному скрипті) ───
// Знаходимо останню позицію обладнання (не послуги)
let lastEquipIdx = -1;
for (let i = lineItemsConverted.length - 1; i >= 0; i--) {
  if (lineItemsConverted[i].category !== 'Послуги') { // послуги йдуть окремо
    lastEquipIdx = i;
    break;
  }
}

if (vatMode === 'with' && lastEquipIdx >= 0) {
  lineItemsConverted[lastEquipIdx].total     = +(lineItemsConverted[lastEquipIdx].total + taxValueConverted).toFixed(2);
  lineItemsConverted[lastEquipIdx].unitPrice = lineItemsConverted[lastEquipIdx].total; // qty=1 — ціна = сума
}

// ────────────────────────────────────────────────────────────────
// 9. ФОРМУВАННЯ ПОЗИЦІЙ ТАБЛИЦІ ДЛЯ ШАБЛОНУ КП
//    Обладнання: r1..r9, Роботи: r10
// ────────────────────────────────────────────────────────────────

const fmtNum = (n) => {
  if (!n && n !== 0) return '';
  return (+n).toLocaleString('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Обладнання + матеріали (всі крім послуг)
const equipItems = lineItemsConverted;   // всі lineItems — без окремого рядку послуг
// Послуги — один рядок із загальною сумою
const serviceTotal = +(servicesSale * currencyRate).toFixed(2);

// Заповнюємо 9 рядків обладнання + 1 рядок послуг
// Ключі з {{ }} — щоб replaceAllText точно матчив {{r1_num}} а не лише r1_num
const tableRows = {};
for (let i = 1; i <= 9; i++) {
  const item = equipItems[i - 1];
  if (item) {
    tableRows[`{{r${i}_num}}`]   = `1.${i}`;
    tableRows[`{{r${i}_name}}`]  = item.name;
    tableRows[`{{r${i}_unit}}`]  = item.unit;
    tableRows[`{{r${i}_qty}}`]   = String(item.qty);
    tableRows[`{{r${i}_price}}`] = fmtNum(item.unitPrice);
    tableRows[`{{r${i}_total}}`] = fmtNum(item.total);
  } else {
    tableRows[`{{r${i}_num}}`]   = '';
    tableRows[`{{r${i}_name}}`]  = '';
    tableRows[`{{r${i}_unit}}`]  = '';
    tableRows[`{{r${i}_qty}}`]   = '';
    tableRows[`{{r${i}_price}}`] = '';
    tableRows[`{{r${i}_total}}`] = '';
  }
}

// Рядок послуг (r10)
tableRows['{{r10_num}}']   = '2.1';
tableRows['{{r10_name}}']  = 'Розробка робочого проекту\nДоставка обладнання та матеріалів\nМонтаж конструкцій\nВстановлення панелей\nСпецтехніка та механізми\nЕлектротехнічні роботи\nАвторський нагляд\nПусконаладка';
tableRows['{{r10_unit}}']  = 'послуга';
tableRows['{{r10_qty}}']   = '1';
tableRows['{{r10_price}}'] = '';
tableRows['{{r10_total}}'] = fmtNum(serviceTotal);

// ────────────────────────────────────────────────────────────────
// 10. ЕКОНОМІЧНИЙ РОЗРАХУНОК (окупність, кредит, деградація)
// ────────────────────────────────────────────────────────────────

const tariffNow     = parseFlt(p.tariff_now)     || 0;   // грн/кВт·год
const creditEnabled = p.credit === 'yes';
const creditRate    = parseFlt(p.credit_rate)    || 9;    // %/рік
const creditMonths  = parseFlt(p.credit_months)  || 60;   // місяців

// Загальна вартість в UAH (для окупності)
const totalUAH = +(finalTotal / currencyRate * rateUSD).toFixed(2);

// ─── Деградація панелей 0.4%/рік (Longi/Trina гарантія) ───
// Перший рік: 99% від номіналу (initial degradation)
// Далі: 0.4%/рік × 25 років = -10% до кінця
const DEGRAD_YEAR1 = 0.990;
const DEGRAD_ANNUAL = 0.004; // 0.4% на рік після першого

// Загальна річна генерація передається з ses_charts — тут розраховуємо за замовчуванням
// (якщо ses_charts запустився після — він перезапише yearly_gen)
// Використовуємо середній коефіцієнт ~1100 год/рік × DC кВт
// Точне значення прийде з ses_charts.js через regional coefficients
const FALLBACK_HOURS = 1100; // середня Україна
let yearlyKWhBase = dcKW * FALLBACK_HOURS * DEGRAD_YEAR1;

// ─── Самоспоживання: 80% генерації клієнт споживає сам ───
const SELF_CONSUMPTION = 0.80;

// ─── Щомісячна економія (рік 1) ───
const monthlyGen     = yearlyKWhBase / 12;
const monthlySavings = monthlyGen * SELF_CONSUMPTION * tariffNow; // грн/міс

// ─── Окупність без кредиту ───
let paybackYears = 0;
let paybackStr   = '—';
if (monthlySavings > 0 && totalUAH > 0) {
  paybackYears = totalUAH / (monthlySavings * 12);
  const pyInt  = Math.floor(paybackYears);
  const pyMon  = Math.round((paybackYears - pyInt) * 12);
  paybackStr   = pyMon > 0 ? `${pyInt} р. ${pyMon} міс.` : `${pyInt} р.`;
}

// ─── Зафіксований тариф на 30 років (середньозважений з деградацією) ───
// totalCost / сумарна генерація за 30 років
let totalGen30 = 0;
for (let yr = 0; yr < 30; yr++) {
  const degrad = yr === 0 ? DEGRAD_YEAR1 : DEGRAD_YEAR1 - DEGRAD_ANNUAL * yr;
  totalGen30 += dcKW * FALLBACK_HOURS * Math.max(degrad, 0.75);
}
const fixedTariff = totalGen30 > 0
  ? +(totalUAH / totalGen30).toFixed(4)
  : 0;

// ─── Загальний дохід за 25 років (з деградацією) ───
let totalProfit25 = 0;
for (let yr = 0; yr < 25; yr++) {
  const degrad    = yr === 0 ? DEGRAD_YEAR1 : DEGRAD_YEAR1 - DEGRAD_ANNUAL * yr;
  const genYr     = dcKW * FALLBACK_HOURS * Math.max(degrad, 0.75);
  totalProfit25  += genYr * SELF_CONSUMPTION * tariffNow;
}
totalProfit25 = Math.round(totalProfit25);

// ─── Кредит ───
let creditVars = {
  '{{credit_b17}}': '', '{{credit_b18}}': '', '{{credit_b19}}': '',
  '{{credit_b20}}': '', '{{credit_b21}}': '', '{{credit_b22}}': '',
  '{{credit_b23}}': '', '{{credit_b24}}': '', '{{credit_b25}}': '',
  '{{credit_b26}}': '', '{{credit_b27}}': '', '{{credit_b28}}': '',
  '{{credit_currency}}': currSign,
  '{{credit_final}}': '',
};

let paybackWithCreditStr = '—';
let monthlyPaymentUAH    = 0;
let remainderAfterCredit = 0;

if (creditEnabled && totalUAH > 0) {
  // Комісія 1.5%
  const commissionUAH  = totalUAH * 0.015;
  const totalWithComm  = totalUAH + commissionUAH;

  // Ануїтетний платіж: M = S × r / (1 − (1+r)^−n)
  const monthlyRate    = creditRate / 100 / 12;
  monthlyPaymentUAH    = monthlyRate > 0
    ? +(totalWithComm * monthlyRate / (1 - Math.pow(1 + monthlyRate, -creditMonths))).toFixed(2)
    : +(totalWithComm / creditMonths).toFixed(2);

  // Залишок після кредиту (сумарна економія за весь термін кредиту - виплати)
  const totalPayments  = monthlyPaymentUAH * creditMonths;
  const totalSavings   = monthlySavings * creditMonths;
  remainderAfterCredit = Math.round(totalSavings - totalPayments);

  // Окупність з кредитом — місяць, коли накопичена економія покриє суму виплат
  let cumSavings = 0, cumPayments = 0;
  let paybackWithCreditMonths = creditMonths;
  for (let m = 1; m <= creditMonths + 12; m++) {
    cumSavings  += monthlySavings;
    cumPayments += m <= creditMonths ? monthlyPaymentUAH : 0;
    if (m > creditMonths && cumSavings >= totalPayments) {
      paybackWithCreditMonths = m;
      break;
    }
  }
  const pwcYears = Math.floor(paybackWithCreditMonths / 12);
  const pwcMon   = paybackWithCreditMonths % 12;
  paybackWithCreditStr = pwcMon > 0 ? `${pwcYears} р. ${pwcMon} міс.` : `${pwcYears} р.`;

  const fmt = n => Math.round(n).toLocaleString('uk-UA');

  creditVars = {
    '{{credit_b17}}': `${fmt(totalUAH)} грн`,                  // Вартість СЕС
    '{{credit_b18}}': `${fmt(monthlySavings)} грн/міс`,        // Щомісячна економія
    '{{credit_b19}}': paybackStr,                               // Окупність без кредиту
    '{{credit_b20}}': `${creditRate}%`,                         // Ставка
    '{{credit_b21}}': `${fmt(monthlyPaymentUAH)} грн/міс`,     // Щомісячний платіж
    '{{credit_b22}}': paybackWithCreditStr,                     // Окупність з кредитом
    '{{credit_b23}}': `${creditMonths} міс.`,                   // Термін
    '{{credit_b24}}': `${fmt(commissionUAH)} грн`,              // Комісія 1.5%
    '{{credit_b25}}': `${fmt(totalWithComm)} грн`,              // Повна вартість з комісією
    '{{credit_b26}}': `${fmt(totalPayments)} грн`,              // Загальна сума виплат
    '{{credit_b27}}': remainderAfterCredit > 0
      ? `+${fmt(remainderAfterCredit)} грн`
      : `${fmt(remainderAfterCredit)} грн`,                     // Залишок після кредиту
    '{{credit_b28}}': `${fmt(totalProfit25)} грн`,              // Прибуток за 25 р.
    '{{credit_currency}}': currSign,
    '{{credit_final}}': `${fmt(totalPayments)} грн`,
  };
}

// ────────────────────────────────────────────────────────────────
// 11. ЗАМІНИ ДЛЯ ШАБЛОНУ GOOGLE DOCS
// ────────────────────────────────────────────────────────────────

const today      = new Date().toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit', year: 'numeric' });
const powerStr   = `${dcKW.toFixed(0)} кВт`;
const powerLabel = `${dcKW.toFixed(0)} кВт DC`;
const managerName = p.manager || '';

const MANAGERS = {
  'Петров Дмитро':        { phone: '+38 (063) 847-49-83', email: 'd.petrov@rayton.com.ua' },
  'Тубіш Микола':         { phone: '+38 (067) 197-57-23', email: 'mt@rayton.com.ua' },
  'Сидоров Максим':       { phone: '+38 (063) 847-49-76', email: 'ms@rayton.com.ua' },
  'Достовалов Олександр': { phone: '+38 (063) 847-49-77', email: 'od@rayton.com.ua' },
  'Стоцький Віталій':     { phone: '+38 (067) 349-79-33', email: 'vs@rayton.com.ua' },
  'Павлов Дмитро':        { phone: '+38 (063) 847-49-76', email: 'dp@rayton.com.ua' },
  'Лисенко Юрій':         { phone: '+38 (063) 847-49-82', email: 'yl@rayton.com.ua' },
};
const mgr = MANAGERS[managerName] || { phone: '', email: '' };

const templateVars = {
  '{{project_title}}':   `Проєкт: "${p.project_name}" ${powerStr}`,
  '{{today_date}}':      today,
  '{{currency}}':        currSign,
  '{{power}}':           powerStr,
  '{{manager_name}}':    managerName,
  '{{manager_phone}}':   mgr.phone,
  '{{manager_email}}':   mgr.email,
  '{{link_site_1}}':     'rayton.com.ua',
  '{{link_site_2}}':     'rayton.com.ua',
  '{{link_youtube}}':    'RaytonSun',
  '{{link_email}}':      'sales@rayton.com.ua',
  '{{project}}':         p.project_name || '',
  '{{project_address}}': '',
  '{{gps_coords}}':      '',
  '{{placement_type}}':  sesType,
  '{{cost_build}}':      fmtNum(dcKW > 0 ? finalTotal / dcKW : 0),
  '{{power1}}':          powerLabel,
  '{{payback}}':         paybackStr,
  '{{yearly_gen}}':      `${Math.round(yearlyKWhBase / 1000)} тис. кВт·год`,
  '{{total_costG}}':     fmtNum(finalTotal),
  '{{total_cost}}':      fmtNum(finalTotal),
  '{{total_profit}}':    `${Math.round(totalProfit25 / 1000)} тис. грн`,
  '{{tariff_now}}':      tariffNow ? `${tariffNow.toFixed(2)} грн/кВт·год` : '',
  '{{tariff_fixed}}':    fixedTariff ? `${fixedTariff.toFixed(4)} грн/кВт·год` : '',
  ...creditVars,
  // Таблиця позицій
  ...tableRows,
};

// ────────────────────────────────────────────────────────────────
// 12. ВИБІР ШАБЛОНУ
// ────────────────────────────────────────────────────────────────

// Google Doc template IDs — скопіюйте з оригінального скрипту
const TEMPLATE_NO_CREDIT_ID = '1Ytn9wssFM-Eg_Fy_CXoZ2CKfd-4uamP39tkhrhf5JMs';
const TEMPLATE_NO_CREDIT_NO_IMG_ID = '1LGbc5siAxP6zg4B87KpInSzHGDK0hYy8bbNDvrPNcp0';

const TEMPLATE_WITH_CREDIT_ID        = '15cW_pHFAmXfHgZ6w2Tv_NZYRDTQnE0eV4l6nnbdsfc4';
const TEMPLATE_WITH_CREDIT_NO_IMG_ID = '1bbW_s6qWlfrjKlmuhheiFCDRusPvbRZi7wz3E0B1DkA';

// Чи є кастомне зображення від техвідділу
const hasCustomImage = !!(p.custom_image_base64);

// Вибір шаблону: 2 змінні (кредит + фото) = 4 варіанти
const selectedTemplateId =
  creditEnabled && hasCustomImage  ? TEMPLATE_WITH_CREDIT_ID :
  creditEnabled && !hasCustomImage ? TEMPLATE_WITH_CREDIT_NO_IMG_ID :
  !creditEnabled && hasCustomImage ? TEMPLATE_NO_CREDIT_ID :
                                     TEMPLATE_NO_CREDIT_NO_IMG_ID;

// Папка для збереження PDF
const DRIVE_PARENT_FOLDER_ID = '1QSNGUZ9e7CAyeZNMJ3EpEUuyXTaSfTky';

// ────────────────────────────────────────────────────────────────
// 12. ВИХІД
// ────────────────────────────────────────────────────────────────

// ────────────────────────────────────────────────────────────────
// DEBUG — видалити після діагностики
// ────────────────────────────────────────────────────────────────
// Пошук панелей у refData для діагностики
const _panelRow = refData.find(r => r.category.toLowerCase() === 'фотоелектричні модулі');
const _panelExact = findRow('Фотоелектричні модулі', p.module_type || '');
const _debug = {
  refData_count:      refData.length,
  panel_categories:   [...new Set(refData.map(r => r.category))].slice(0, 8),
  panel_names_solar:  refData.filter(r => r.category.toLowerCase() === 'фотоелектричні модулі').map(r => r.name),
  p_module_type:      p.module_type,
  p_panel_qty:        panelQty,
  panel_row_found:    !!_panelExact,
  panel_row_sample:   _panelRow,
  line_items_count:   lineItems.length,
  sumSale_debug:      sumSale,
  rateEUR,
  rateUSD,
};

return [{
  json: {
    // ─── Ідентифікатори для наступних вузлів ───
    templateDocId:     selectedTemplateId,
    driveFolderId:     DRIVE_PARENT_FOLDER_ID,
    chat_id:           p.chat_id,

    // ─── Мета ───
    project_name:      p.project_name,
    manager:           p.manager,
    region:            p.region,
    power_label:       powerLabel,
    currency:          currency,
    currency_sign:     currSign,
    vat_mode:          vatMode,
    today:             today,

    // ─── Фінансові підсумки ───
    total_usd:         +(finalTotal / currencyRate).toFixed(2),
    total_display:     fmtNum(finalTotal),
    total_currency:    finalTotal,
    tax_usd:           taxValue,
    tax_display:       fmtNum(taxValueConverted),

    // ─── Деталі розрахунку (для логів/дебагу) ───
    dc_kw:             dcKW,
    ac_kw:             acKW,
    panel_qty:         panelQty,
    panel_watt:        panelWatt,
    sum_sale_usd:      +sumSale.toFixed(2),
    sum_purchase_usd:  +sumPurchase.toFixed(2),
    actual_price_per_kw: +(finalTotal / dcKW).toFixed(2),
    target_price_per_kw: parseFlt(p.price_per_kw),
    rate_usd:          rateUSD,
    rate_eur:          rateEUR,

    // ─── Економіка (для ses_charts.js і для шаблону) ───
    tariff_now:        tariffNow,
    yearly_kwh_base:   +yearlyKWhBase.toFixed(0),
    monthly_savings_uah: +monthlySavings.toFixed(2),
    payback_str:       paybackStr,
    payback_years:     +paybackYears.toFixed(2),
    fixed_tariff:      fixedTariff,
    total_profit_25:   totalProfit25,
    credit_enabled:    creditEnabled,
    credit_rate:       creditRate,
    credit_months:     creditMonths,
    monthly_payment_uah: monthlyPaymentUAH,
    payback_with_credit: paybackWithCreditStr,

    // ─── Позиції для шаблону ───
    line_items:        lineItemsConverted,

    // ─── Заміни для Google Docs (replaceText) ───
    template_vars:     templateVars,

    // ─── Візуалізація СЕС ───
    has_custom_image:    hasCustomImage,
    custom_image_base64: p.custom_image_base64 || null,
    custom_image_mime:   p.custom_image_mime   || 'image/jpeg',

    // ─── Назва файлу ───
    file_name: `КП_Рейтон_${p.project_name || 'Проект'}_${powerStr.replace(' ', '_')}_${today.replace(/\./g, '-')}.pdf`,
    doc_copy_name: `Пропозиція_${p.project_name || 'Проект'}_${powerStr}_${Date.now()}`,

    // ─── DEBUG ───
    _debug,
  }
}];

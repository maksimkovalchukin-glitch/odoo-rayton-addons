/* ================================================================
   calculate-engine.js — Розрахунок КП СЕС (браузер)
   Порт логіки n8n/ses_calculate.js на клієнтську сторону.

   Використання:
     const result = CalculateEngine.calculate(formData, window.CATALOG);
     // result: { ok, lineItems, totals, templateVars, economicData, ... }
================================================================ */

window.CalculateEngine = (function () {

  // ── Утиліти ────────────────────────────────────────────────────

  function parseFlt(v) {
    if (v === null || v === undefined || v === '') return 0;
    return parseFloat(String(v).replace(/\s/g, '').replace(',', '.')) || 0;
  }

  function fmtNum(n) {
    if (!n && n !== 0) return '';
    return (+n).toLocaleString('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // ── Мітки для сервісних позицій ────────────────────────────────

  function getMontageLabel(kw) {
    if (kw <= 80)   return '50-80 кВт';
    if (kw <= 100)  return '80-100 кВт';
    if (kw <= 250)  return '100-250 кВт';
    if (kw <= 500)  return '250-500 кВт';
    if (kw <= 1000) return '500-1000 кВт';
    return '1000 та більше';
  }

  function getTechLabel(sesType, kw) {
    if (sesType === 'Наземна') return 'наземка за кВт';
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

  // ── Головна функція розрахунку ──────────────────────────────────

  function calculate(p, catalog) {
    if (!catalog) return { ok: false, error: 'catalog not loaded' };

    // ─── Вхідні параметри ───────────────────────────────────────

    const dcKW     = parseFlt(p.real_dc);
    const acKW     = parseFlt(p.real_ac);
    const panelQty = parseInt(p.panel_qty) || 0;

    const sesType = p.ses_type || 'Дахова';
    const matType = (p.material_type || 'DC та AC').toLowerCase();
    const isDC    = matType.includes('dc');
    const isAC    = matType.includes('ac');

    const currency     = p.currency || 'USD';
    const vatMode      = p.price_vat_type === 'без ПДВ' ? 'without' : 'with';
    const rateEUR      = parseFlt(catalog.rates?.eur_uah) || 43.5;
    const rateUSD      = parseFlt(catalog.rates?.usd_uah) || 41.2;
    const currencyRate = currency === 'EUR' ? rateUSD / rateEUR : 1;
    const currSign     = currency === 'EUR' ? '€' : '$';

    // Інвертори (до 3 типів)
    const inverters = [];
    for (let i = 1; i <= 3; i++) {
      const model = p[`inverter_${i}_model`];
      const qty   = parseInt(p[`inverter_${i}_qty`]) || 0;
      if (model && qty > 0) inverters.push({ model, qty });
    }

    // Типи кріплення [{type, qty}]
    // Якщо передано один mount_type + panel_qty — конвертуємо
    let mountTypes = Array.isArray(p.mount_types) ? p.mount_types : [];
    if (mountTypes.length === 0 && p.mount_type && panelQty > 0) {
      mountTypes = [{ type: p.mount_type, qty: panelQty }];
    }

    // Визначаємо панельну потужність з каталогу по full_name
    const panelEntry = (catalog.panels || []).find(
      pp => pp.full_name === p.module_type
    );
    const panelWatt = panelEntry?.watt || parseFlt(p.module_watt) || 620;

    const rangeDC = dcKW <= 100 ? 'small' : 'large';
    const rangeAC = dcKW <= 100 ? 'small' : 'large';

    // ─── Markup Map (мутує при ітерації) ─────────────────────────

    // Збираємо початкові markup-и з каталогу
    const markupMap = new Map();

    function mkKey(type, name) {
      return `${type}|${(name || '').toLowerCase()}`;
    }

    (catalog.mounting || []).forEach(m => {
      markupMap.set(mkKey('mounting', m.name), m.markup ?? 2.0);
    });
    (catalog.materials_dc || []).forEach(m => {
      markupMap.set(mkKey('materials_dc', m.mount_name), m.markup ?? 1.6);
    });
    (catalog.materials_ac || []).forEach(m => {
      markupMap.set(mkKey('materials_ac', m.mount_name), m.markup ?? 1.6);
    });
    (catalog.montage || []).forEach(m => {
      markupMap.set(mkKey('montage', m.label), m.markup ?? 1.5);
    });
    (catalog.tech || []).forEach(m => {
      markupMap.set(mkKey('tech', m.label), m.markup ?? 1.5);
    });
    (catalog.delivery || []).forEach(m => {
      markupMap.set(mkKey('delivery', m.label), m.markup ?? 1.5);
    });

    // Фіксовані категорії (не змінюємо при ітерації)
    const FIXED_TYPES = new Set(['panel', 'inverter', 'monitoring', 'power_regulation']);

    const MARKUP_LIMITS = {
      mounting:    catalog.markup_limits?.mounting   || [1.0, 7.1875],
      materials_dc:catalog.markup_limits?.materials  || [1.0, 6.75],
      materials_ac:catalog.markup_limits?.materials  || [1.0, 6.75],
      montage:     catalog.markup_limits?.montage    || [1.0, 3.0188],
      tech:        catalog.markup_limits?.tech       || [1.0, 3.0188],
      delivery:    catalog.markup_limits?.delivery   || [1.0, 3.0188],
    };

    // ─── Функція розрахунку ───────────────────────────────────────

    function calculateAll() {
      let sumSale = 0, sumPurchase = 0;
      const lineItems = [];
      let servicesSale = 0;

      function addLine(type, name, price, markup, qty, unit, label) {
        if (!price || qty <= 0) return 0;
        const mu   = markup || 1;
        const sale = price * mu * qty;
        const pur  = price * qty;
        sumSale     += sale;
        sumPurchase += pur;
        lineItems.push({
          category: type,
          name: label || name,
          unit: unit || 'шт.',
          qty,
          unitPriceUSD: +(price * mu).toFixed(4),
          totalUSD:     +sale.toFixed(4),
        });
        return sale;
      }

      // Панелі
      if (panelEntry && panelQty > 0) {
        const dispName = (p.module_type || '').replace(/^Фотоелектричні модулі\s*/i, '').trim();
        addLine('panel', p.module_type, panelEntry.price_usd, panelEntry.markup,
          panelQty, 'шт.', `Фотогальванічний модуль ${dispName}`);
      }

      // Інвертори
      inverters.forEach(inv => {
        const entry = (catalog.inverters || []).find(i => i.name === inv.model);
        if (!entry) return;
        addLine('inverter', inv.model, entry.price_usd, entry.markup,
          inv.qty, 'шт.', `Інвертор ${inv.model}`);
      });

      // Моніторинг
      const monEntry = (catalog.monitoring || []).find(m => m.name === p.monitoring_device);
      if (monEntry) {
        addLine('monitoring', monEntry.name, monEntry.price_usd, monEntry.markup,
          1, 'шт.', `Моніторинг ${monEntry.name}`);
      }

      // Регулювання потужності
      const prEntry = (catalog.power_regulation || []).find(m => m.name === p.power_regulation);
      if (prEntry) {
        addLine('power_regulation', prEntry.name, prEntry.price_usd, prEntry.markup,
          1, 'компл.', `Регулювання потужності ${prEntry.name}`);
      }

      // Кріплення (зважена ціна по типах)
      let mountSale = 0, mountPurchase = 0, mountTotalQty = 0;
      mountTypes.forEach(mt => {
        const mEntry = (catalog.mounting || []).find(m => m.name === mt.type);
        if (!mEntry || mt.qty <= 0) return;
        const mu = markupMap.get(mkKey('mounting', mt.type)) ?? mEntry.markup ?? 2.0;
        mountSale     += mEntry.price_per_panel_usd * mu * mt.qty;
        mountPurchase += mEntry.price_per_panel_usd * mt.qty;
        mountTotalQty += mt.qty;
      });
      if (mountTotalQty > 0) {
        sumSale     += mountSale;
        sumPurchase += mountPurchase;
        lineItems.push({
          category: 'mounting',
          name: 'Кріплення фотомодулів',
          unit: 'компл.',
          qty: 1,
          unitPriceUSD: +mountSale.toFixed(4),
          totalUSD:     +mountSale.toFixed(4),
        });
      }

      // Матеріали DC / AC
      let matSale = 0, matPurchase = 0;
      mountTypes.forEach(mt => {
        const allocKW = (mt.qty * panelWatt) / 1000;

        if (isDC) {
          const dcEntry = (catalog.materials_dc || []).find(m => m.mount_name === mt.type);
          if (dcEntry) {
            const price = rangeDC === 'small' ? dcEntry.price_per_kw_small : dcEntry.price_per_kw_large;
            const mu    = markupMap.get(mkKey('materials_dc', mt.type)) ?? dcEntry.markup ?? 1.6;
            matSale     += price * mu * allocKW;
            matPurchase += price * allocKW;
          }
        }
        if (isAC) {
          const acEntry = (catalog.materials_ac || []).find(m => m.mount_name === mt.type);
          if (acEntry) {
            const price = rangeAC === 'small' ? acEntry.price_per_kw_small : acEntry.price_per_kw_large;
            const mu    = markupMap.get(mkKey('materials_ac', mt.type)) ?? acEntry.markup ?? 1.6;
            matSale     += price * mu * allocKW;
            matPurchase += price * allocKW;
          }
        }
      });

      // Додаткові матеріали
      const extraPrice = parseFlt(catalog.extra_materials_usd);
      if (extraPrice > 0) {
        matSale     += extraPrice;
        matPurchase += extraPrice;
      }

      if (matSale > 0) {
        let matLabel = 'PV кабель, конектори MC4, автоматика струмового захисту, монтажний комплект (короб, лоток, гофротруби, трансформатори, ізоляційні матеріали і т.д)';
        if (isDC && isAC) matLabel += ' + AC';
        else if (isAC)   matLabel += ' AC';
        sumSale     += matSale;
        sumPurchase += matPurchase;
        lineItems.push({
          category: 'materials',
          name: matLabel,
          unit: 'компл.',
          qty: 1,
          unitPriceUSD: +matSale.toFixed(4),
          totalUSD:     +matSale.toFixed(4),
        });
      }

      // Сервіси (монтаж + техніка + доставка)
      const montLabel    = getMontageLabel(dcKW);
      const techLbl      = getTechLabel(sesType, dcKW);
      const deliveryLbl  = getDeliveryLabel(dcKW);
      const techQty      = sesType === 'Наземна' ? dcKW : 1;

      function addService(type, catalog_arr, label, qty) {
        const entry = (catalog_arr || []).find(s => s.label === label);
        if (!entry) return;
        const mu = markupMap.get(mkKey(type, label)) ?? entry.markup ?? 1.5;
        const price = entry.price_usd || entry.price_per_kw_usd || 0;
        const s   = price * mu * qty;
        const pur = price * qty;
        servicesSale += s;
        sumSale      += s;
        sumPurchase  += pur;
      }

      addService('montage', catalog.montage, montLabel, dcKW);
      addService('tech',    catalog.tech,    techLbl,   techQty);
      addService('delivery',catalog.delivery,deliveryLbl, 1);

      return { sumSale, sumPurchase, lineItems, servicesSale };
    }

    // ─── Ітераційне коригування ───────────────────────────────────

    let targetPricePerKWinUSD = parseFlt(p.price_per_kw) || 380;
    if (currency === 'EUR') {
      targetPricePerKWinUSD = targetPricePerKWinUSD / currencyRate;
    }

    if (dcKW > 0) {
      for (let iter = 0; iter < 30; iter++) {
        const { sumSale, sumPurchase } = calculateAll();
        if (sumSale === 0) break;

        let _ss = sumSale, _sp = sumPurchase, _tv = 0;
        if (vatMode === 'with') {
          for (let i = 0; i < 2; i++) {
            _tv = ((_ss - _sp) / 1.025 * 0.24) + (_ss * 0.013);
            _ss += _tv; _sp += _tv;
          }
        }
        const estimatedFinalUSD    = sumSale + (vatMode === 'with' ? _tv : 0);
        const actualPricePerKWinUSD = estimatedFinalUSD / dcKW;
        const scaleFactor = targetPricePerKWinUSD / actualPricePerKWinUSD;

        if (Math.abs(scaleFactor - 1) < 0.000001) break;

        markupMap.forEach((markup, key) => {
          const [type] = key.split('|');
          if (FIXED_TYPES.has(type)) return;
          const [minM, maxM] = MARKUP_LIMITS[type] || [1, 5];
          markupMap.set(key, +Math.max(minM, Math.min(markup * scaleFactor, maxM)).toFixed(6));
        });
      }
    }

    // ─── Фінальний розрахунок ─────────────────────────────────────

    const { sumSale, sumPurchase, lineItems, servicesSale } = calculateAll();

    // ЄП (2 ітерації)
    let spSumSale = sumSale, spSumPurchase = sumPurchase, taxValue = 0;
    if (vatMode === 'with') {
      for (let i = 0; i < 2; i++) {
        taxValue       = ((spSumSale - spSumPurchase) / 1.025 * 0.24) + (spSumSale * 0.013);
        spSumSale     += taxValue;
        spSumPurchase += taxValue;
      }
    }
    taxValue = +taxValue.toFixed(2);

    const taxConverted          = +(taxValue * currencyRate).toFixed(2);
    const totalBeforeTax        = +(sumSale * currencyRate).toFixed(2);
    const totalWithTax          = +(totalBeforeTax + taxConverted).toFixed(2);
    const finalTotal            = vatMode === 'with' ? totalWithTax : totalBeforeTax;

    // Конвертуємо позиції
    const lineItemsConverted = lineItems.map(item => ({
      ...item,
      unitPrice: +(item.unitPriceUSD * currencyRate).toFixed(2),
      total:     +(item.totalUSD     * currencyRate).toFixed(2),
    }));

    // ЄП до останньої позиції обладнання
    if (vatMode === 'with') {
      let lastEquipIdx = -1;
      for (let i = lineItemsConverted.length - 1; i >= 0; i--) {
        if (lineItemsConverted[i].category !== 'services') { lastEquipIdx = i; break; }
      }
      if (lastEquipIdx >= 0) {
        lineItemsConverted[lastEquipIdx].total     = +(lineItemsConverted[lastEquipIdx].total + taxConverted).toFixed(2);
        lineItemsConverted[lastEquipIdx].unitPrice = lineItemsConverted[lastEquipIdx].total;
      }
    }

    // ─── Таблиця рядків для шаблону ───────────────────────────────

    const serviceTotal = +(servicesSale * currencyRate).toFixed(2);
    const tableRows = {};
    for (let i = 1; i <= 9; i++) {
      const item = lineItemsConverted[i - 1];
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
    tableRows['{{r10_num}}']   = '2.1';
    tableRows['{{r10_name}}']  = 'Розробка робочого проекту\nДоставка обладнання та матеріалів\nМонтаж конструкцій\nВстановлення панелей\nСпецтехніка та механізми\nЕлектротехнічні роботи\nАвторський нагляд\nПусконаладка';
    tableRows['{{r10_unit}}']  = 'послуга';
    tableRows['{{r10_qty}}']   = '1';
    tableRows['{{r10_price}}'] = '';
    tableRows['{{r10_total}}'] = fmtNum(serviceTotal);

    // ─── Економіка ────────────────────────────────────────────────

    const tariffNow      = parseFlt(p.tariff_now) || 0;
    const creditEnabled  = p.credit === 'yes';
    const creditRate     = parseFlt(p.credit_rate) || 9;
    const creditMonths   = parseFlt(p.credit_months) || 60;
    const totalUAH       = +(finalTotal / currencyRate * rateUSD).toFixed(2);

    const DEGRAD_YEAR1 = 0.990;
    const DEGRAD_ANNUAL = 0.004;
    const FALLBACK_HOURS = 1100;
    const SELF_CONSUMPTION = 0.80;

    let yearlyKWhBase = dcKW * FALLBACK_HOURS * DEGRAD_YEAR1;
    const monthlyGen = yearlyKWhBase / 12;
    const monthlySavings = monthlyGen * SELF_CONSUMPTION * tariffNow;

    let paybackYears = 0, paybackStr = '—';
    if (monthlySavings > 0 && totalUAH > 0) {
      paybackYears = totalUAH / (monthlySavings * 12);
      const pyInt  = Math.floor(paybackYears);
      const pyMon  = Math.round((paybackYears - pyInt) * 12);
      paybackStr   = pyMon > 0 ? `${pyInt} р. ${pyMon} міс.` : `${pyInt} р.`;
    }

    let totalGen30 = 0;
    for (let yr = 0; yr < 30; yr++) {
      const degrad = yr === 0 ? DEGRAD_YEAR1 : DEGRAD_YEAR1 - DEGRAD_ANNUAL * yr;
      totalGen30 += dcKW * FALLBACK_HOURS * Math.max(degrad, 0.75);
    }
    const fixedTariff = totalGen30 > 0 ? +(totalUAH / totalGen30).toFixed(4) : 0;

    let totalProfit25 = 0;
    for (let yr = 0; yr < 25; yr++) {
      const degrad = yr === 0 ? DEGRAD_YEAR1 : DEGRAD_YEAR1 - DEGRAD_ANNUAL * yr;
      totalProfit25 += dcKW * FALLBACK_HOURS * Math.max(degrad, 0.75) * SELF_CONSUMPTION * tariffNow;
    }
    totalProfit25 = Math.round(totalProfit25);

    // ─── Кредит ───────────────────────────────────────────────────

    let creditVars = {
      '{{credit_b17}}': '', '{{credit_b18}}': '', '{{credit_b19}}': '',
      '{{credit_b20}}': '', '{{credit_b21}}': '', '{{credit_b22}}': '',
      '{{credit_b23}}': '', '{{credit_b24}}': '', '{{credit_b25}}': '',
      '{{credit_b26}}': '', '{{credit_b27}}': '', '{{credit_b28}}': '',
      '{{credit_currency}}': currSign, '{{credit_final}}': '',
    };

    let paybackWithCreditStr = '—', monthlyPaymentUAH = 0;

    if (creditEnabled && totalUAH > 0) {
      const commissionUAH = totalUAH * 0.015;
      const totalWithComm = totalUAH + commissionUAH;
      const monthlyRate   = creditRate / 100 / 12;
      monthlyPaymentUAH   = monthlyRate > 0
        ? +(totalWithComm * monthlyRate / (1 - Math.pow(1 + monthlyRate, -creditMonths))).toFixed(2)
        : +(totalWithComm / creditMonths).toFixed(2);

      const totalPayments  = monthlyPaymentUAH * creditMonths;
      const totalSavings   = monthlySavings * creditMonths;
      const remainder      = Math.round(totalSavings - totalPayments);
      let pwcMonths = creditMonths;
      let cumSav = 0;
      for (let m = 1; m <= creditMonths + 12; m++) {
        cumSav += monthlySavings;
        if (m > creditMonths && cumSav >= totalPayments) { pwcMonths = m; break; }
      }
      const pwcY = Math.floor(pwcMonths / 12);
      const pwcM = pwcMonths % 12;
      paybackWithCreditStr = pwcM > 0 ? `${pwcY} р. ${pwcM} міс.` : `${pwcY} р.`;

      const fmt = n => Math.round(n).toLocaleString('uk-UA');
      creditVars = {
        '{{credit_b17}}': `${fmt(totalUAH)} грн`,
        '{{credit_b18}}': `${fmt(monthlySavings)} грн/міс`,
        '{{credit_b19}}': paybackStr,
        '{{credit_b20}}': `${creditRate}%`,
        '{{credit_b21}}': `${fmt(monthlyPaymentUAH)} грн/міс`,
        '{{credit_b22}}': paybackWithCreditStr,
        '{{credit_b23}}': `${creditMonths} міс.`,
        '{{credit_b24}}': `${fmt(commissionUAH)} грн`,
        '{{credit_b25}}': `${fmt(totalWithComm)} грн`,
        '{{credit_b26}}': `${fmt(totalPayments)} грн`,
        '{{credit_b27}}': remainder > 0 ? `+${fmt(remainder)} грн` : `${fmt(remainder)} грн`,
        '{{credit_b28}}': `${fmt(totalProfit25)} грн`,
        '{{credit_currency}}': currSign,
        '{{credit_final}}': `${fmt(totalPayments)} грн`,
      };
    }

    // ─── Template vars ─────────────────────────────────────────────

    const today      = new Date().toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const powerStr   = `${dcKW.toFixed(0)} кВт`;
    const powerLabel = `${dcKW.toFixed(0)} кВт DC`;

    const templateVars = {
      '{{project_title}}':   `Проєкт: "${p.project_name}" ${powerStr}`,
      '{{today_date}}':      today,
      '{{currency}}':        currSign,
      '{{power}}':           powerStr,
      '{{manager_name}}':    p.manager || '',
      '{{manager_phone}}':   p.manager_phone || '',
      '{{manager_email}}':   p.manager_email || '',
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
      ...tableRows,
    };

    // ─── Повертаємо результат ─────────────────────────────────────

    return {
      ok: true,

      // Параметри станції
      dc_kw:        dcKW,
      ac_kw:        acKW,
      panel_qty:    panelQty,
      panel_watt:   panelWatt,

      // Фінансові підсумки
      final_total:       finalTotal,
      total_usd:         +(finalTotal / currencyRate).toFixed(2),
      total_display:     fmtNum(finalTotal),
      tax_usd:           taxValue,
      tax_display:       fmtNum(taxConverted),
      currency,
      currency_sign:     currSign,
      vat_mode:          vatMode,
      actual_price_per_kw: +(finalTotal / (dcKW || 1)).toFixed(2),

      // Курси
      rate_usd: rateUSD,
      rate_eur: rateEUR,

      // Позиції
      line_items: lineItemsConverted,
      service_total: serviceTotal,

      // Економіка
      tariff_now:          tariffNow,
      yearly_kwh_base:     +yearlyKWhBase.toFixed(0),
      monthly_savings_uah: +monthlySavings.toFixed(2),
      payback_str:         paybackStr,
      payback_years:       +paybackYears.toFixed(2),
      fixed_tariff:        fixedTariff,
      total_profit_25:     totalProfit25,
      total_uah:           totalUAH,
      credit_enabled:      creditEnabled,
      credit_rate:         creditRate,
      credit_months:       creditMonths,
      monthly_payment_uah: monthlyPaymentUAH,
      payback_with_credit: paybackWithCreditStr,

      // Для Google Docs
      template_vars:  templateVars,
      today,
      power_label:    powerLabel,
      project_name:   p.project_name || '',
      manager:        p.manager || '',
      region:         p.region || '',
      file_name: `КП_Рейтон_${p.project_name || 'Проект'}_${powerStr.replace(' ', '_')}_${today.replace(/\./g, '-')}.pdf`,
      doc_copy_name: `Пропозиція_${p.project_name || 'Проект'}_${powerStr}_${Date.now()}`,
    };
  }

  return { calculate };

})();

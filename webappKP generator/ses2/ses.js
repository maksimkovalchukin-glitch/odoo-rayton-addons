/* ======================================================
   SES WIZARD — Генератор КП v2
   Кроки: 1-Проект, 2-Режим, 3-Параметри,
          4-Обладнання, 5-Інвертори, 6-Ціна, 7-Preview
====================================================== */

const WEBHOOK_URL = "https://n8n.rayton.net/webhook/ses-kp";

const tg = window.Telegram?.WebApp || null;
if (tg) { tg.expand(); tg.ready(); }

/* ======================================================
   ДОВІДНИКИ
====================================================== */

const MOUNT_TYPES = [
  "блочки",
  "сітка",
  "баластна сітка",
  "баластна сітка з противагою",
  "гвинт-шуруп",
  "схід-захід",
  "схід-захід (без баласту) деш.",
  "схід-захід (без баласту) дор.",
  "з підйомом",
  "з підйомом без баласту",
  "наземка",
  "наземка схід-захід",
];

// label — відображення в UI
// name  — точна назва колонки B таблиці (з категорією-префіксом → унікальний матчинг)
const _CP = 'Фотоелектричні модулі';
const PANELS = [
  { label: "Тrina 575W",  name: `${_CP} Тrina 575W`,  watt: 575 },
  { label: "Тrina 580W",  name: `${_CP} Тrina 580W`,  watt: 580 },
  { label: "Тrina 610W",  name: `${_CP} Тrina 610W`,  watt: 610 },
  { label: "Тrina 710W",  name: `${_CP} Тrina 710W`,  watt: 710 },
  { label: "JA 625W",     name: `${_CP} JA 625W`,     watt: 625 },
  { label: "Longi 580W",  name: `${_CP} Longi 580W`,  watt: 580 },
  { label: "Longi 610W",  name: `${_CP} Longi 610W`,  watt: 610 },
  { label: "Trina 625W",  name: `${_CP} Trina 625W`,  watt: 625 },
  { label: "Trina 620W",  name: `${_CP} Trina 620W`,  watt: 620 },
];

// Інвертори: roof — без 115кВт, ground — повний список
const INVERTERS_ROOF = [
  { name: "Huawei SUN2000-150KTL-G0", power: 150 },
  { name: "Huawei SUN2000-100KTL-M2", power: 100 },
  { name: "Huawei SUN2000-50KTL-M3",  power: 50  },
  { name: "Huawei SUN2000-30KTL-M3",  power: 30  },
];

const INVERTERS_GROUND = [
  { name: "Huawei SUN2000-150KTL-G0",  power: 150 },
  { name: "Huawei SUN2000-115KTL-M2",  power: 115 },
  { name: "Huawei SUN2000-100KTL-M2",  power: 100 },
  { name: "Huawei SUN2000-50KTL-M3",   power: 50  },
  { name: "Huawei SUN2000-30KTL-M3",   power: 30  },
];

const CONFIG = {
  dcAcRatio:        1.28,
  minRatio:         1.1,
  maxRatio:         1.5,
  wPerM2Tilted:     130.55,   // Вт/м² — похилий дах
  wPerM2Flat:       229.33,   // Вт/м² — плоский дах
  genPer100kW:      18000,    // кВт·год/рік на 100 кВт
  minAC:            100,
  minConsumptionMWh: 10,
};

/* ======================================================
   СТАН ДОДАТКУ
====================================================== */

const state = {
  step: 1,
  totalSteps: 9,
  mode: null,           // consumption | power | roof | manual
  sesType: "roof",      // roof | ground
  inverterMode: "auto", // auto | manual
  manualInputMode: "qty", // qty | power  (для manual режиму step3)
  autoInverters: null,  // { list: [...], totalAC }
  manualInverters: [],
  currency: "USD",
  vat: "with",   // with | without
  credit: "no",  // yes | no
  customImageBase64: null,  // base64 рядок або null
  customImageMime: null,    // "image/jpeg" тощо
};

/* ======================================================
   ІНІЦІАЛІЗАЦІЯ SELECTS
====================================================== */

function fillPanelSelects() {
  ["module_type", "manual_module"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    PANELS.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.name;       // name — точна назва з таблиці (для матчингу в n8n)
      opt.textContent = p.label; // label — коротке читабельне ім'я для UI
      sel.appendChild(opt);
    });
  });
}

/* ======================================================
   КРІПЛЕННЯ — ДИНАМІЧНИЙ СПИСОК
====================================================== */

let mountIdCounter = 0;

function buildMountSelect(selectedValue = "") {
  const sel = document.createElement("select");
  sel.className = "mount-type-select";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "Оберіть тип";
  sel.appendChild(empty);
  MOUNT_TYPES.forEach(mt => {
    const opt = document.createElement("option");
    opt.value = mt;
    opt.textContent = mt;
    if (mt === selectedValue) opt.selected = true;
    sel.appendChild(opt);
  });
  return sel;
}

function addMountRow(mountType = "", qty = "") {
  const id = ++mountIdCounter;
  const list = document.getElementById("mountList");

  const row = document.createElement("div");
  row.className = "mount-row";
  row.dataset.mountId = id;

  const sel = buildMountSelect(mountType);
  sel.addEventListener("change", updateMountSummary);

  const input = document.createElement("input");
  input.type = "number";
  input.min = "1";
  input.placeholder = "Панелей";
  input.className = "mount-qty-input";
  input.value = qty;
  input.addEventListener("input", updateMountSummary);

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "mount-remove-btn";
  removeBtn.textContent = "✕";
  removeBtn.addEventListener("click", () => {
    row.remove();
    toggleRemoveButtons();
    updateMountSummary();
  });

  row.appendChild(sel);
  row.appendChild(input);
  row.appendChild(removeBtn);
  list.appendChild(row);

  toggleRemoveButtons();
  updateMountSummary();
}

function toggleRemoveButtons() {
  const rows = document.querySelectorAll(".mount-row");
  rows.forEach(row => {
    row.querySelector(".mount-remove-btn").style.display =
      rows.length > 1 ? "block" : "none";
  });
}

function getMountEntries() {
  const rows = document.querySelectorAll(".mount-row");
  const result = [];
  rows.forEach(row => {
    const type = row.querySelector(".mount-type-select").value;
    const qty  = parseInt(row.querySelector(".mount-qty-input").value) || 0;
    if (type && qty > 0) result.push({ type, qty });
  });
  return result;
}

function updateMountSummary() {
  const entries = getMountEntries();
  const summaryEl = document.getElementById("mountSummary");
  if (!summaryEl) return;

  if (entries.length === 0) {
    summaryEl.style.display = "none";
    return;
  }

  const total = entries.reduce((s, e) => s + e.qty, 0);
  const expectedTotal = getTotalPanels();

  let html = `<div class="mount-total">Всього панелей: <strong>${total}</strong>`;
  if (expectedTotal > 0) {
    const diff = expectedTotal - total;
    if (diff === 0) {
      html += ` <span class="mount-ok">✅ збігається</span>`;
    } else if (diff > 0) {
      html += ` <span class="mount-warn">⚠️ не вистачає ${diff}</span>`;
    } else {
      html += ` <span class="mount-warn">⚠️ на ${Math.abs(diff)} більше</span>`;
    }
  }
  html += `</div>`;

  if (entries.length > 1) {
    html += `<div class="mount-breakdown">`;
    entries.forEach(e => {
      const pct = total > 0 ? Math.round(e.qty / total * 100) : 0;
      html += `<div class="mount-breakdown-row">
        <span class="mount-type-label">${e.type}</span>
        <span class="mount-type-qty">${e.qty} шт · ${pct}%</span>
      </div>`;
    });
    html += `</div>`;
  }

  summaryEl.style.display = "block";
  summaryEl.innerHTML = html;
}

function getTotalPanels() {
  const watt = getPanelWatt();
  if (!watt) return 0;
  const dc = getTargetDC();
  if (!dc) return 0;
  return Math.ceil(dc / (watt / 1000));
}

function fillInverterSelects() {
  const list = state.sesType === "ground" ? INVERTERS_GROUND : INVERTERS_ROOF;
  ["inv1_model", "inv2_model", "inv3_model"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    // Зберігаємо поточне значення
    const prev = sel.value;
    sel.innerHTML = '<option value="">— не вибрано —</option>';
    list.forEach(inv => {
      const opt = document.createElement("option");
      opt.value = inv.power;
      opt.textContent = inv.name;
      sel.appendChild(opt);
    });
    // Відновлюємо якщо є
    if (prev) sel.value = prev;
  });
}

/* ======================================================
   ПРОГРЕС-БАР
====================================================== */

function updateProgress() {
  const pct = ((state.step - 1) / (state.totalSteps - 1)) * 100;
  document.getElementById("progressBar").style.width = pct + "%";

  const labels = ["", "Проект", "Режим", "Параметри", "Обладнання", "Інвертори", "Кріплення", "Ціна", "Економіка", "Підтвердження"];
  document.getElementById("stepLabel").textContent = `Крок ${state.step} з ${state.totalSteps} · ${labels[state.step]}`;
}

/* ======================================================
   НАВІГАЦІЯ МІЖ КРОКАМИ
====================================================== */

function showStep(n) {
  for (let i = 1; i <= state.totalSteps; i++) {
    const el = document.getElementById("step" + i);
    if (el) el.style.display = i === n ? "block" : "none";
  }
  state.step = n;
  updateProgress();

  document.getElementById("btnBack").style.display = n > 1 ? "inline-block" : "none";

  const nextBtn = document.getElementById("btnNext");
  if (n === state.totalSteps) {
    nextBtn.textContent = "Надіслати КП →";
    nextBtn.classList.add("submit-btn");
  } else {
    nextBtn.textContent = "Далі →";
    nextBtn.classList.remove("submit-btn");
  }

  // Telegram back button
  if (tg) {
    if (n > 1) {
      tg.BackButton.show();
      tg.BackButton.onClick(() => goBack());
    } else {
      tg.BackButton.hide();
    }
  }

  // Спеціальні дії при вході в крок
  if (n === 5) onEnterInverterStep();
  if (n === 6) onEnterMountStep();
  if (n === 8) onEnterEconomyStep();
  if (n === 9) buildSummary();

  window.scrollTo(0, 0);
}

function goNext() {
  const err = validateStep(state.step);
  if (err) {
    showError(err);
    return;
  }

  if (state.step === 5) {
    // Якщо ручний режим — перевірити що хоч один інвертор заданий
    if (state.inverterMode === "manual") {
      const total = getManualAC();
      if (total <= 0) {
        showError("Оберіть хоча б один інвертор і вкажіть кількість");
        return;
      }
    }
  }

  if (state.step === 5 && state.inverterMode === "auto") {
    // "Прийняти" вже перевірено вище — просто переходимо
  }

  if (state.step < state.totalSteps) {
    showStep(state.step + 1);
  } else {
    submitKP();
  }
}

function goBack() {
  if (state.step > 1) showStep(state.step - 1);
}

/* ======================================================
   ВАЛІДАЦІЯ КРОКІВ
====================================================== */

function validateStep(step) {
  switch (step) {
    case 1: {
      if (!val("project_name")) return "Введіть назву проєкту";
      if (!val("manager"))      return "Оберіть менеджера";
      if (!val("region"))       return "Оберіть регіон";
      return null;
    }
    case 2: {
      if (!state.mode) return "Оберіть режим розрахунку";
      return null;
    }
    case 3: {
      if (state.mode === "consumption") {
        const mwh = num("monthly_consumption");
        if (!mwh || mwh < CONFIG.minConsumptionMWh)
          return `Мінімальне споживання ${CONFIG.minConsumptionMWh} МВт·год/міс`;
      }
      if (state.mode === "power") {
        const kw = num("planned_power");
        if (!kw || kw < 50) return "Мінімальна потужність 50 кВт";
      }
      if (state.mode === "roof") {
        const area = num("roof_area");
        const type = val("roof_type");
        if (!area || area < 100) return "Мінімальна площа 100 м²";
        if (!type) return "Оберіть тип даху";
        const dc = calcRoofDC(area, type);
        if (dc < 50) return "Площа замала — DC менше 50 кВт";
      }
      if (state.mode === "manual") {
        if (!val("manual_module")) return "Оберіть тип панелей";
        if (state.manualInputMode === "qty") {
          const qty = num("manual_panel_qty");
          if (!qty || qty < 1) return "Вкажіть кількість панелей";
        } else {
          const dc = num("manual_dc_power");
          if (!dc || dc < 50) return "Мінімальна потужність 50 кВт";
        }
      }
      return null;
    }
    case 4: {
      if (state.mode !== "manual" && !val("module_type")) return "Оберіть тип панелей";
      return null;
    }
    case 5: return null;
    case 6: {
      const mounts = getMountEntries();
      if (mounts.length === 0) return "Додайте хоча б один тип кріплення";
      return null;
    }
    case 7: {
      const price = num("price_per_kw");
      if (!price || price < 200) return "Вкажіть цільову ціну за кВт (мін. 200)";
      return null;
    }
    case 8: {
      const tariff = num("tariff_now");
      if (!tariff || tariff < 0.5) return "Вкажіть поточний тариф клієнта (грн/кВт·год)";
      if (state.credit === "yes") {
        const rate = num("credit_rate");
        const months = num("credit_months");
        if (!rate || rate < 1) return "Вкажіть відсоткову ставку";
        if (!months || months < 6) return "Вкажіть термін кредиту (мін. 6 місяців)";
      }
      return null;
    }
    default: return null;
  }
}

/* ======================================================
   РЕЖИМ (STEP 2)
====================================================== */

function selectMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-card").forEach(c => {
    c.classList.toggle("active", c.dataset.mode === mode);
  });

  // Показати потрібний param-block на кроці 3
  ["consumption", "power", "roof", "manual"].forEach(m => {
    const el = document.getElementById("param_" + m);
    if (el) el.style.display = m === mode ? "block" : "none";
  });

  // Налаштування step3 title
  const titles = {
    consumption: "Споживання клієнта",
    power:       "Планова потужність",
    roof:        "Площа даху",
    manual:      "Склад обладнання",
  };
  document.getElementById("step3Title").textContent = titles[mode] || "Параметри";

  // В manual — поле панелей на кроці 4 не потрібне
  const moduleField = document.getElementById("moduleField");
  if (moduleField) {
    moduleField.style.display = mode === "manual" ? "none" : "block";
  }
}

/* ======================================================
   РОЗРАХУНОК ПОТУЖНОСТІ
====================================================== */

function calcRoofDC(area, roofType) {
  const coef = roofType === "tilted" ? CONFIG.wPerM2Tilted : CONFIG.wPerM2Flat;
  return (area * coef) / 1000;
}

function calcConsumptionAC(mwh) {
  const kwh = mwh * 1000;
  let ac = (kwh / CONFIG.genPer100kW) * 100;
  ac = Math.ceil(ac / 50) * 50; // округлення до 50
  return Math.max(ac, CONFIG.minAC);
}

function getTargetDC() {
  if (state.mode === "consumption") {
    const mwh = num("monthly_consumption");
    const ac = calcConsumptionAC(mwh);
    return ac * CONFIG.dcAcRatio;
  }
  if (state.mode === "power") {
    return num("planned_power") || 0;
  }
  if (state.mode === "roof") {
    return calcRoofDC(num("roof_area"), val("roof_type"));
  }
  if (state.mode === "manual") {
    const watt = PANELS.find(p => p.name === val("manual_module"))?.watt || 0;
    if (state.manualInputMode === "power") {
      return num("manual_dc_power") || 0;
    }
    const qty = num("manual_panel_qty");
    return (watt * qty) / 1000;
  }
  return 0;
}

/* ======================================================
   ПІДБІР ІНВЕРТОРІВ
====================================================== */

function getInverterList() {
  return state.sesType === "ground" ? INVERTERS_GROUND : INVERTERS_ROOF;
}

function selectBestInverters(targetAC) {
  const list = getInverterList();
  const sorted = [...list].sort((a, b) => b.power - a.power);

  // Жадібний підбір від більших до менших
  let remaining = targetAC;
  const result = [];

  sorted.forEach(inv => {
    if (inv.power >= 100) {
      const qty = Math.floor(remaining / inv.power);
      if (qty > 0) {
        result.push({ ...inv, qty });
        remaining -= qty * inv.power;
      }
    }
  });

  // Добираємо залишок малими
  if (remaining > 0) {
    for (const inv of sorted) {
      if (inv.power < 100) {
        const qty = Math.ceil(remaining / inv.power);
        if (qty > 0) {
          result.push({ ...inv, qty });
          break;
        }
      }
    }
  }

  if (result.length === 0) return null;

  const totalAC = result.reduce((s, i) => s + i.power * i.qty, 0);
  return { list: result, totalAC };
}

/* ======================================================
   КРОК 5 — ВІДОБРАЖЕННЯ ІНВЕРТОРІВ
====================================================== */

function onEnterMountStep() {
  const inv = getSelectedInverters();
  const ac  = inv.reduce((s, i) => s + i.power * i.qty, 0);
  const dc  = getTargetDC(); // DC від панелей
  const watt = getPanelWatt();
  const panelQty = watt ? Math.ceil(dc / (watt / 1000)) : 0;

  const hint = document.getElementById("mountPanelHint");
  if (hint) {
    hint.innerHTML = panelQty > 0
      ? `Всього панелей за розрахунком: <strong>${panelQty} шт</strong> · DC <strong>${dc.toFixed(0)} кВт</strong>`
      : "Дані про кількість панелей ще невідомі";
    hint.style.display = "block";
  }

  // Оновлюємо expected в summary
  updateMountSummary();
}

function onEnterInverterStep() {
  // Оновити тип СЕС зі step4
  const sesTypeEl = document.getElementById("ses_type");
  state.sesType = sesTypeEl ? sesTypeEl.value : "roof";

  // Оновити списки інверторів у ручному режимі
  fillInverterSelects();

  const targetDC = getTargetDC();
  const targetAC = targetDC / CONFIG.dcAcRatio;

  state.autoInverters = selectBestInverters(Math.max(targetAC, CONFIG.minAC));

  renderAutoSuggestion(targetDC);
}

function renderAutoSuggestion(targetDC) {
  const result = state.autoInverters;
  const cardsEl  = document.getElementById("inverterCards");
  const summaryEl = document.getElementById("inverterSummary");
  const ratioEl   = document.getElementById("ratioBar");

  if (!result) {
    cardsEl.innerHTML = '<div class="inv-error">Не вдалось підібрати інвертори</div>';
    return;
  }

  // Картки
  cardsEl.innerHTML = result.list.map(inv => `
    <div class="inv-card">
      <div class="inv-qty-badge">${inv.qty}×</div>
      <div class="inv-power">${inv.power} кВт</div>
      <div class="inv-name">${inv.name}</div>
    </div>
  `).join("");

  // Розрахунок (DC — від панелей, а не від інверторів)
  const realAC = result.totalAC;
  const panelWatt = getPanelWatt();
  const panelQty  = panelWatt ? Math.ceil(targetDC / (panelWatt / 1000)) : "?";
  const ratio = targetDC / realAC;

  summaryEl.innerHTML = `
    <div class="summary-row"><span>DC потужність</span><strong>${targetDC.toFixed(1)} кВт</strong></div>
    <div class="summary-row"><span>AC потужність</span><strong>${realAC.toFixed(0)} кВт</strong></div>
    <div class="summary-row"><span>Кількість панелей</span><strong>${panelQty} шт</strong></div>
  `;

  renderRatioBar(ratio, ratioEl);
}

function getPanelWatt() {
  if (state.mode === "manual") {
    return PANELS.find(p => p.name === val("manual_module"))?.watt || 0;
  }
  return PANELS.find(p => p.name === val("module_type"))?.watt || 0;
}

function renderRatioBar(ratio, el) {
  const ok = ratio >= CONFIG.minRatio && ratio <= CONFIG.maxRatio;
  const color = ok ? "#22c55e" : "#f59e0b";
  const icon  = ok ? "✅" : "⚠️";
  el.innerHTML = `
    <div class="ratio-display" style="color:${color}">
      ${icon} DC/AC = ${ratio.toFixed(2)}
      <span class="ratio-norm">(норма ${CONFIG.minRatio}–${CONFIG.maxRatio})</span>
    </div>
  `;
}

/* --- Ручний режим інверторів --- */

function getManualAC() {
  let total = 0;
  [1, 2, 3].forEach(i => {
    const power = num(`inv${i}_model`);
    const qty   = num(`inv${i}_qty`);
    if (power && qty) total += power * qty;
  });
  return total;
}

function updateManualSummary() {
  const realAC = getManualAC();
  if (!realAC) {
    document.getElementById("manualSummary").innerHTML = "";
    document.getElementById("manualRatioBar").innerHTML = "";
    return;
  }

  const realDC = getTargetDC();
  const ratio  = realDC / realAC;
  const panelWatt = getPanelWatt();
  const panelQty  = panelWatt ? Math.ceil(realDC / (panelWatt / 1000)) : "?";

  document.getElementById("manualSummary").innerHTML = `
    <div class="summary-row"><span>DC потужність</span><strong>${realDC.toFixed(1)} кВт</strong></div>
    <div class="summary-row"><span>AC потужність</span><strong>${realAC.toFixed(0)} кВт</strong></div>
    <div class="summary-row"><span>Кількість панелей</span><strong>${panelQty} шт</strong></div>
  `;

  renderRatioBar(ratio, document.getElementById("manualRatioBar"));
}

/* ======================================================
   LIVE ПІДКАЗКИ (step 3)
====================================================== */

function updateRoofHint() {
  const area = num("roof_area");
  const type = val("roof_type");
  const hint = document.getElementById("roofCalcHint");
  if (!area || !type || !hint) return;

  const dc = calcRoofDC(area, type);
  const ac = dc / CONFIG.dcAcRatio;
  hint.style.display = "block";
  hint.innerHTML = `Орієнтовна DC потужність: <strong>${dc.toFixed(0)} кВт</strong> · AC: <strong>${ac.toFixed(0)} кВт</strong>`;
}

function updatePriceLabel() {
  const sign = state.currency === "EUR" ? "€" : "$";
  const vatStr = state.vat === "with" ? "з ПДВ" : "без ПДВ";
  document.getElementById("priceLabel").textContent = `Ціна за кВт (${sign} ${vatStr})`;
}

function updateManualDCHint() {
  const watt = num("manual_module");
  const box  = document.getElementById("manualDCBox");
  if (!box) return;

  if (state.manualInputMode === "qty") {
    const qty = num("manual_panel_qty");
    if (!watt || !qty) { box.style.display = "none"; return; }
    const dc = (watt * qty) / 1000;
    box.style.display = "block";
    box.innerHTML = `DC: <strong>${dc.toFixed(1)} кВт</strong> · Рекомендований AC: <strong>${(dc / CONFIG.dcAcRatio).toFixed(0)} кВт</strong>`;
  } else {
    const dc = num("manual_dc_power");
    if (!watt || !dc) { box.style.display = "none"; return; }
    const qty = Math.ceil(dc / (watt / 1000));
    box.style.display = "block";
    box.innerHTML = `Кількість панелей: <strong>${qty} шт</strong> · Рекомендований AC: <strong>${(dc / CONFIG.dcAcRatio).toFixed(0)} кВт</strong>`;
  }
}

/* ======================================================
   ЕКОНОМІКА (STEP 8)
====================================================== */

function onEnterEconomyStep() {
  updateEconomyHint();
}

function updateEconomyHint() {
  const tariff = num("tariff_now");
  const hint   = document.getElementById("economyHint");
  if (!hint) return;

  if (!tariff) { hint.style.display = "none"; return; }

  // Орієнтовна річна генерація (з конфігу, якщо вже є)
  const inv    = getSelectedInverters();
  const ac     = inv.reduce((s, i) => s + i.power * i.qty, 0);
  const dc     = ac > 0 ? ac * CONFIG.dcAcRatio : getTargetDC();
  // ~1100 год/рік (середня Україна)
  const yearlyKWh = dc * 1100;
  if (!yearlyKWh) { hint.style.display = "none"; return; }

  const yearlySavingsUAH = yearlyKWh * tariff;
  const priceKW          = num("price_per_kw") || 0;
  const totalUSD         = priceKW * dc;
  // Орієнтовний курс для preview
  const approxUAHperUSD  = 41;
  const totalUAH         = totalUSD * approxUAHperUSD;
  const paybackYears     = totalUAH > 0 && yearlySavingsUAH > 0
    ? (totalUAH / yearlySavingsUAH).toFixed(1) : null;

  let html = `Орієнтована річна генерація: <strong>${Math.round(yearlyKWh / 1000)} тис. кВт·год</strong><br>`;
  html    += `Річна економія: <strong>${Math.round(yearlySavingsUAH / 1000)} тис. грн</strong>`;
  if (paybackYears) html += `<br>Приблизна окупність: <strong>${paybackYears} р.</strong>`;

  hint.style.display = "block";
  hint.innerHTML = html;
}

/* ======================================================
   PREVIEW (STEP 7)
====================================================== */

function buildSummary() {
  const inv = getSelectedInverters();
  const dc  = getTargetDC();
  const ac  = inv.reduce((s, i) => s + i.power * i.qty, 0);
  const panelWatt = getPanelWatt();
  const panelQty  = panelWatt ? Math.ceil((ac * CONFIG.dcAcRatio) / (panelWatt / 1000)) : "?";

  const modeLabels = {
    consumption: `${val("monthly_consumption")} МВт·год/міс`,
    power:       `${val("planned_power")} кВт DC`,
    roof:        `${val("roof_area")} м² · ${val("roof_type") === "tilted" ? "похилий" : "плоский"}`,
    manual:      `${val("manual_panel_qty")} шт × ${val("manual_module")} Вт`,
  };

  const panelLabel = state.mode === "manual"
    ? PANELS.find(p => p.name === val("manual_module"))?.label || "—"
    : PANELS.find(p => p.name === val("module_type"))?.label || "—";

  const currSign = state.currency === "EUR" ? "€" : "$";

  const invLines = inv.map(i => `${i.qty}× ${i.name}`).join("<br>");

  document.getElementById("summaryBlock").innerHTML = `
    <div class="summary-section">
      <div class="summary-row"><span>Проєкт</span><strong>${val("project_name")}</strong></div>
      <div class="summary-row"><span>Менеджер</span><strong>${val("manager")}</strong></div>
      <div class="summary-row"><span>Регіон</span><strong>${val("region")}</strong></div>
    </div>
    <div class="summary-section">
      <div class="summary-row"><span>Режим</span><strong>${state.mode}</strong></div>
      <div class="summary-row"><span>Вхідні дані</span><strong>${modeLabels[state.mode]}</strong></div>
    </div>
    <div class="summary-section">
      <div class="summary-row"><span>Панелі</span><strong>${panelLabel}</strong></div>
      <div class="summary-row"><span>Кількість панелей</span><strong>${panelQty} шт</strong></div>
      <div class="summary-row"><span>DC потужність</span><strong>${(ac * CONFIG.dcAcRatio).toFixed(1)} кВт</strong></div>
      <div class="summary-row"><span>AC потужність</span><strong>${ac.toFixed(0)} кВт</strong></div>
      <div class="summary-row"><span>Інвертори</span><strong>${invLines}</strong></div>
    </div>
    <div class="summary-section">
      <div class="summary-row"><span>Кріплення</span><strong>${getMountEntries().map(e => `${e.type} ${e.qty}шт`).join(", ")}</strong></div>
      <div class="summary-row"><span>Матеріали</span><strong>${val("material_type") === "dc_ac" ? "DC та AC" : "Тільки DC"}</strong></div>
      <div class="summary-row"><span>Тип СЕС</span><strong>${val("ses_type") === "ground" ? "Наземна" : "Дахова"}</strong></div>
    </div>
    <div class="summary-section">
      <div class="summary-row"><span>Ціна за кВт</span><strong>${val("price_per_kw")} ${currSign} ${state.vat === "with" ? "з ПДВ" : "без ПДВ"}</strong></div>
    </div>
    <div class="summary-section">
      <div class="summary-row"><span>Тариф клієнта</span><strong>${val("tariff_now")} грн/кВт·год</strong></div>
      <div class="summary-row"><span>Кредитування</span><strong>${state.credit === "yes" ? `Так · ${val("credit_rate")}%/рік · ${val("credit_months")} міс.` : "Без кредиту"}</strong></div>
    </div>
  `;
}

/* ======================================================
   ЗБІР ІНВЕРТОРІВ ДЛЯ ВІДПРАВКИ
====================================================== */

function getSelectedInverters() {
  if (state.inverterMode === "auto" && state.autoInverters) {
    return state.autoInverters.list;
  }
  // Ручний режим
  const result = [];
  [1, 2, 3].forEach(i => {
    const power = num(`inv${i}_model`);
    const qty   = num(`inv${i}_qty`);
    if (power && qty > 0) {
      const inv = getInverterList().find(x => x.power === power);
      result.push({ name: inv?.name || `${power}кВт`, power, qty });
    }
  });
  return result;
}

/* ======================================================
   ВІДПРАВКА
====================================================== */

async function submitKP() {
  const nextBtn = document.getElementById("btnNext");
  nextBtn.disabled = true;
  nextBtn.textContent = "Надсилаємо...";

  const inv = getSelectedInverters();
  const ac  = inv.reduce((s, i) => s + i.power * i.qty, 0);
  const dc  = getTargetDC(); // DC від панелей, не від інверторів
  const panelWatt = getPanelWatt();
  const panelQty  = panelWatt ? Math.ceil(dc / (panelWatt / 1000)) : 0;

  const chatId = tg?.initDataUnsafe?.chat?.id || tg?.initDataUnsafe?.user?.id || null;

  const panelLabel = state.mode === "manual"
    ? PANELS.find(p => p.name === val("manual_module"))?.label || ""
    : PANELS.find(p => p.name === val("module_type"))?.label || "";

  const payload = {
    calculation_mode:   state.mode,
    project_name:       val("project_name"),
    manager:            val("manager"),
    region:             val("region"),

    // Вхідні дані (залежно від режиму)
    monthly_consumption: state.mode === "consumption" ? num("monthly_consumption") : null,
    planned_power:       state.mode === "power"       ? num("planned_power")       : null,
    roof_area:           state.mode === "roof"        ? num("roof_area")           : null,
    roof_type:           state.mode === "roof"        ? val("roof_type")           : null,

    // Обладнання
    // module_type = p.name — точна назва з таблиці (для матчингу в n8n)
    module_type:        state.mode === "manual" ? val("manual_module") : val("module_type"),
    module_watt:        panelWatt,
    panel_qty:          panelQty,
    real_dc:            +dc.toFixed(2),
    real_ac:            +ac.toFixed(2),

    // Інвертори (до 3 типів)
    inverter_1_model:   inv[0]?.name  || "",
    inverter_1_qty:     inv[0]?.qty   || 0,
    inverter_2_model:   inv[1]?.name  || "",
    inverter_2_qty:     inv[1]?.qty   || 0,
    inverter_3_model:   inv[2]?.name  || "",
    inverter_3_qty:     inv[2]?.qty   || 0,

    ses_type:           val("ses_type") === "ground" ? "Наземна" : "Дахова",
    mount_types:        getMountEntries(),
    material_type:      val("material_type") === "dc_ac" ? "DC та AC" : "DC",
    power_regulation:   val("power_regulation"),
    monitoring_device:  val("monitoring_device"),

    currency:           state.currency,
    price_vat:          state.vat,   // "with" | "without"
    price_per_kw:       num("price_per_kw"),

    // Економіка
    tariff_now:         num("tariff_now"),
    credit:             state.credit,  // "yes" | "no"
    credit_rate:        state.credit === "yes" ? num("credit_rate")   : null,
    credit_months:      state.credit === "yes" ? num("credit_months") : null,

    // Візуалізація СЕС (base64, опціонально)
    custom_image_base64: state.customImageBase64 || null,
    custom_image_mime:   state.customImageMime   || null,

    chat_id: chatId,
  };

  try {
    await fetch(WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (tg) {
      tg.showAlert("КП формується та буде надіслано в цей чат");
      setTimeout(() => tg.close(), 800);
    } else {
      alert("КП надіслано! N8n обробляє запит.");
      nextBtn.textContent = "Надіслано ✅";
    }
  } catch (err) {
    nextBtn.disabled = false;
    nextBtn.textContent = "Помилка. Спробуйте ще";
  }
}

/* ======================================================
   УТИЛІТИ
====================================================== */

function val(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : "";
}

function num(id) {
  return parseFloat(val(id)) || 0;
}

function showError(msg) {
  // Видаляємо попередню помилку
  const old = document.getElementById("errorToast");
  if (old) old.remove();

  const toast = document.createElement("div");
  toast.id = "errorToast";
  toast.className = "error-toast";
  toast.textContent = msg;
  document.querySelector(".app").appendChild(toast);

  setTimeout(() => toast.remove(), 3000);
}

/* ======================================================
   ІНІЦІАЛІЗАЦІЯ ПОДІЙ
====================================================== */

document.addEventListener("DOMContentLoaded", () => {

  fillPanelSelects();
  fillInverterSelects();

  // Кнопки навігації
  document.getElementById("btnNext").addEventListener("click", goNext);
  document.getElementById("btnBack").addEventListener("click", goBack);

  // Вибір режиму
  document.querySelectorAll(".mode-card").forEach(card => {
    card.addEventListener("click", () => selectMode(card.dataset.mode));
  });

  // Зміна типу СЕС → оновити списки інверторів
  document.getElementById("ses_type").addEventListener("change", function() {
    state.sesType = this.value;
    fillInverterSelects();
  });

  // Live підказки
  document.getElementById("roof_area")?.addEventListener("input", updateRoofHint);
  document.getElementById("roof_type")?.addEventListener("change", updateRoofHint);
  document.getElementById("manual_module")?.addEventListener("change", updateManualDCHint);
  document.getElementById("manual_panel_qty")?.addEventListener("input", updateManualDCHint);
  document.getElementById("manual_dc_power")?.addEventListener("input", updateManualDCHint);

  // Перемикач qty / power в manual режимі
  document.querySelectorAll(".input-mode-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      state.manualInputMode = btn.dataset.inputMode;
      document.querySelectorAll(".input-mode-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("inputByQty").style.display   = state.manualInputMode === "qty"   ? "flex" : "none";
      document.getElementById("inputByPower").style.display = state.manualInputMode === "power" ? "flex" : "none";
      updateManualDCHint();
    });
  });

  // Прийняти авто-підбір
  document.getElementById("btnAccept").addEventListener("click", () => {
    state.inverterMode = "auto";
    goNext();
  });

  // Перейти в ручний режим
  document.getElementById("btnOverride").addEventListener("click", () => {
    state.inverterMode = "manual";
    document.getElementById("inverterSuggestion").style.display = "none";
    document.getElementById("inverterManual").style.display = "block";
  });

  // Повернутись до авто
  document.getElementById("btnBackAuto").addEventListener("click", () => {
    state.inverterMode = "auto";
    document.getElementById("inverterSuggestion").style.display = "block";
    document.getElementById("inverterManual").style.display = "none";
  });

  // Live оновлення в ручному режимі інверторів
  [1, 2, 3].forEach(i => {
    document.getElementById(`inv${i}_model`)?.addEventListener("change", updateManualSummary);
    document.getElementById(`inv${i}_qty`)?.addEventListener("input", updateManualSummary);
  });

  // Перемикання валюти
  document.querySelectorAll(".currency-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      state.currency = btn.dataset.currency;
      document.querySelectorAll(".currency-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      updatePriceLabel();
    });
  });

  // Перемикання ПДВ
  document.querySelectorAll(".vat-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      state.vat = btn.dataset.vat;
      document.querySelectorAll(".vat-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      updatePriceLabel();
    });
  });

  // Кріплення — ініціалізація першого рядка
  addMountRow();
  document.getElementById("btnAddMount").addEventListener("click", () => addMountRow());

  // Кредит toggle
  document.querySelectorAll(".credit-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      state.credit = btn.dataset.credit;
      document.querySelectorAll(".credit-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("creditFields").style.display =
        state.credit === "yes" ? "block" : "none";
      updateEconomyHint();
    });
  });

  // Live підказка в економіці
  document.getElementById("tariff_now")?.addEventListener("input", updateEconomyHint);
  document.getElementById("credit_rate")?.addEventListener("input", updateEconomyHint);

  // Завантаження картинки візуалізації СЕС
  document.getElementById("custom_image")?.addEventListener("change", function() {
    const file = this.files[0];
    if (!file) return;

    // Перевірка розміру (макс 8 МБ)
    if (file.size > 8 * 1024 * 1024) {
      showError("Зображення завелике. Максимум 8 МБ");
      this.value = "";
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target.result;
      // Зберігаємо тільки base64 частину (без "data:image/jpeg;base64,")
      const [meta, b64] = dataUrl.split(",");
      state.customImageBase64 = b64;
      state.customImageMime   = file.type || "image/jpeg";

      // Показуємо preview
      document.getElementById("imgPreview").src      = dataUrl;
      document.getElementById("imgPreviewWrap").style.display = "block";
      document.getElementById("imgUploadBtn").style.display   = "none";
      document.getElementById("imgUploadLabel").textContent   = file.name;
    };
    reader.readAsDataURL(file);
  });

  document.getElementById("imgRemoveBtn")?.addEventListener("click", () => {
    state.customImageBase64 = null;
    state.customImageMime   = null;
    document.getElementById("custom_image").value              = "";
    document.getElementById("imgPreviewWrap").style.display   = "none";
    document.getElementById("imgUploadBtn").style.display     = "flex";
  });

  // Старт
  showStep(1);
});

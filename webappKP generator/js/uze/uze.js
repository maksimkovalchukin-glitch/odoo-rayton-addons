/* ======================================================
   uze.js — Форма + Preview генерації КП УЗЕ
====================================================== */

const N8N_UZE_URL      = 'https://n8n.rayton.net/webhook/kp';
const MANAGERS_URL     = 'https://n8n.rayton.net/webhook/managers';
const MANAGERS_STORAGE = 'rayton_managers';

// ── Preview state ───────────────────────────────────────────────
let pvState    = null;   // { qty, currency, uze_vat, equip_vat, uze_price_per_unit, line_items }
let pvFormData = null;   // original form values
let pvModel    = null;   // model object from catalog
let pvCalc     = null;   // initial calc result (for template_id, tail_pages etc.)

function fmtNum(n) {
  const v = parseFloat(n);
  return isNaN(v) ? '' : Math.round(v).toLocaleString('uk-UA');
}

document.addEventListener('DOMContentLoaded', () => {
  const tgApp = window.Telegram?.WebApp;
  if (tgApp) {
    tgApp.expand();
    tgApp.ready();
    tgApp.BackButton.show();
    tgApp.BackButton.onClick(() => { window.location.href = '../index.html'; });
  }

  loadManagers();
  waitForCatalog();

  document.getElementById('uze_model').addEventListener('change', onModelChange);
  document.getElementById('submitBtn').addEventListener('click', onSubmit);
  document.getElementById('pvBackBtn').addEventListener('click', showForm);
  document.getElementById('pvSendBtn').addEventListener('click', sendKP);
});

// ── Чекаємо каталог ────────────────────────────────────────────

function waitForCatalog() {
  if (window.UZE_CATALOG) {
    populateModels();
    return;
  }
  window.addEventListener('catalogReady', populateModels, { once: true });
  // Fallback — статичні дані
  setTimeout(() => {
    if (!window.UZE_CATALOG && window.UZE_CATALOG_DATA) {
      window.UZE_CATALOG = window.UZE_CATALOG_DATA;
      populateModels();
    }
  }, 3000);
}

// ── Заповнення моделей з каталогу ─────────────────────────────

function populateModels() {
  const catalog = window.UZE_CATALOG;
  if (!catalog?.models) return;

  const sel = document.getElementById('uze_model');
  sel.innerHTML = '<option value="">Оберіть модель УЗЕ</option>';

  catalog.models.forEach(m => {
    const hasPrice = (m.scenarios || []).some(sc => sc.uze_price?.sell_novat_usd > 0);
    const opt = document.createElement('option');
    opt.value = m.name;
    opt.textContent = m.name;
    opt.style.color = hasPrice ? '#2e7d32' : '#c62828';
    sel.appendChild(opt);
  });

  onModelChange();
}

// ── Оновлення доступної кількості ─────────────────────────────

function onModelChange() {
  const catalog = window.UZE_CATALOG;
  if (!catalog?.models) return;

  const sel       = document.getElementById('uze_model');
  const modelName = sel.value;
  const model     = catalog.models.find(m => m.name === modelName);
  const wrap      = document.getElementById('qtyWrap');
  document.getElementById('qtyError').textContent = '';

  // Підсвічуємо select за наявністю ціни
  if (!modelName) {
    sel.style.color = '';
  } else {
    const hasPrice = (model?.scenarios || []).some(sc => sc.uze_price?.sell_novat_usd > 0);
    sel.style.color = hasPrice ? '#2e7d32' : '#c62828';
  }

  if (!model) {
    wrap.innerHTML = '<select id="uze_qty" disabled style="width:100%"><option value="">Спочатку оберіть модель</option></select>';
    return;
  }

  if (model.unlimited) {
    wrap.innerHTML = '<input id="uze_qty" type="number" min="1" max="1000" value="1" style="width:100%;padding:10px;border:1px solid #e0e0e0;border-radius:10px;font-size:15px" />';
  } else {
    const options = model.scenarios.map(s => `<option value="${s.qty}">${s.qty}</option>`).join('');
    wrap.innerHTML = `<select id="uze_qty" style="width:100%">${options}</select>`;
  }
}

// ── Завантаження менеджерів ────────────────────────────────────

const DEFAULT_MANAGERS = [
  { name: 'Петров Дмитро',        phone: '+38 (063) 847-49-83', email: 'd.petrov@rayton.com.ua', telegram: '', active: true },
  { name: 'Тубіш Микола',         phone: '+38 (067) 197-57-23', email: 'mt@rayton.com.ua',        telegram: '', active: true },
  { name: 'Сидоров Максим',       phone: '+38 (063) 847-49-76', email: 'ms@rayton.com.ua',        telegram: '', active: true },
  { name: 'Достовалов Олександр', phone: '+38 (063) 847-49-77', email: 'od@rayton.com.ua',        telegram: '', active: true },
  { name: 'Стоцький Віталій',     phone: '+38 (067) 349-79-33', email: 'vs@rayton.com.ua',        telegram: '', active: true },
  { name: 'Павлов Дмитро',        phone: '+38 (063) 847-49-76', email: 'dp@rayton.com.ua',        telegram: '', active: true },
  { name: 'Лисенко Юрій',         phone: '+38 (063) 847-49-82', email: 'yl@rayton.com.ua',        telegram: '', active: true },
];

async function loadManagers() {
  let managers = [];
  try {
    const res  = await fetch(MANAGERS_URL, { cache: 'no-store' });
    const data = await res.json();
    managers   = data.managers || [];
    if (managers.length) localStorage.setItem(MANAGERS_STORAGE, JSON.stringify(managers));
  } catch {
    const stored = localStorage.getItem(MANAGERS_STORAGE);
    if (stored) managers = JSON.parse(stored);
  }
  if (!managers.length) managers = DEFAULT_MANAGERS;

  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  const sel    = document.getElementById('manager');
  sel.innerHTML = '<option value="">Оберіть менеджера</option>';

  managers.filter(m => m.active !== false).forEach(m => {
    const opt = document.createElement('option');
    opt.value         = m.telegram || m.name;
    opt.textContent   = m.name;
    opt.dataset.name  = m.name;
    opt.dataset.phone = m.phone || '';
    opt.dataset.email = m.email || '';
    if (tgUser?.username && m.telegram && tgUser.username.toLowerCase() === m.telegram.toLowerCase()) {
      opt.selected = true;
    }
    sel.appendChild(opt);
  });
}

// ── Submit → показати preview ───────────────────────────────────

async function onSubmit() {
  const btn   = document.getElementById('submitBtn');
  const errEl = document.getElementById('formError');
  errEl.textContent = '';

  const projectName = document.getElementById('project_name').value.trim();
  const managerSel  = document.getElementById('manager');
  const managerOpt  = managerSel.options[managerSel.selectedIndex];
  const modelName   = document.getElementById('uze_model').value;
  const qtyRaw      = document.getElementById('uze_qty').value;

  if (!projectName)      { errEl.textContent = 'Введіть назву проєкту'; return; }
  if (!managerSel.value) { errEl.textContent = 'Оберіть менеджера'; return; }
  if (!modelName)        { errEl.textContent = 'Оберіть модель УЗЕ'; return; }

  const tg     = window.Telegram?.WebApp;
  const chatId = tg?.initDataUnsafe?.user?.id || tg?.initDataUnsafe?.chat?.id || '';

  pvFormData = {
    project_name:   projectName,
    manager:        managerSel.value,
    manager_name:   managerOpt?.dataset?.name  || '',
    manager_phone:  managerOpt?.dataset?.phone || '',
    manager_email:  managerOpt?.dataset?.email || '',
    region:         document.getElementById('region').value,
    uze_model:      modelName,
    uze_qty:        parseInt(qtyRaw) || 1,
    uze_vat:        document.getElementById('uze_vat').value,
    equipment_vat:  document.getElementById('equipment_vat').value,
    currency:       document.getElementById('currency').value,
    usage_type:     document.getElementById('usage_type').value,
    delivery_term:  document.getElementById('delivery_term').value,
    payment_terms:  document.getElementById('payment_terms').value,
    delivery_terms: "DAP. Доставка до об'єкту Замовника без послуг по розвантаженню",
    chat_id:        String(chatId),
  };

  const catalog = window.UZE_CATALOG;
  if (!catalog) { errEl.textContent = 'Каталог не завантажено. Спробуйте ще раз.'; return; }

  pvCalc = window.UZECalculateEngine?.calculate(pvFormData, catalog);
  if (!pvCalc?.ok) { errEl.textContent = pvCalc?.error || 'Помилка розрахунку'; return; }

  pvModel = (catalog.models || []).find(m => m.name === modelName);

  pvState = {
    qty:               pvFormData.uze_qty,
    currency:          pvFormData.currency,
    uze_vat:           pvFormData.uze_vat,
    equip_vat:         pvFormData.equipment_vat,
    uze_price_per_unit: pvCalc.uze_price_per_unit,
    line_items:        pvCalc.line_items.map(item => ({ ...item })),
  };

  showPreview();
}

// ── Preview: відображення ───────────────────────────────────────

function showForm() {
  document.getElementById('uzePreview').style.display = 'none';
  document.getElementById('uzeForm').style.display    = '';
}

function showPreview() {
  document.getElementById('uzeForm').style.display    = 'none';
  document.getElementById('uzePreview').style.display = '';
  document.getElementById('pvError').textContent = '';

  const { project_name, uze_model, uze_qty, currency } = pvFormData;
  const currSign = currency === 'EUR' ? '€' : '$';

  document.getElementById('pvSummary').innerHTML = `
    <div style="font-size:13px;color:#555;display:flex;flex-direction:column;gap:4px">
      <div><b>Проєкт:</b> ${project_name}</div>
      <div><b>Модель:</b> ${uze_model}</div>
      <div><b>Кількість:</b> ${uze_qty} шт · ${pvModel?.capacity_kwh * uze_qty || '?'} кВт·год</div>
      <div><b>Менеджер:</b> ${pvFormData.manager_name || pvFormData.manager}</div>
    </div>`;

  renderPvUzePrice();
  renderPvEquipment();
  renderPvTotals();
}

function renderPvUzePrice() {
  const { uze_price_per_unit, qty, currency, uze_vat } = pvState;
  const currSign    = currency === 'EUR' ? '€' : '$';
  const uze_total   = uze_price_per_unit * qty;
  const capacityKwh = (pvModel?.capacity_kwh || 0) * qty;
  const equip_total = pvState.line_items.reduce((s, e) => s + e.total, 0);
  const total       = uze_total + equip_total;
  const perKwh      = capacityKwh > 0 ? (total / capacityKwh).toFixed(2) : '—';

  document.getElementById('pvUzePrice').innerHTML = `
    <div style="display:flex;align-items:center;gap:8px">
      <span style="flex:1;font-size:13px;color:#444">${uze_vat}</span>
      <input type="number" step="0.01" id="pvUzeInput" value="${uze_price_per_unit}"
        style="width:110px;padding:6px;border:1px solid #FFC400;border-radius:8px;font-size:14px;font-weight:600;text-align:right"
        oninput="onPvUzePriceChange()" />
      <span style="font-size:12px;color:#888;flex-shrink:0">${currSign}/шт</span>
    </div>
    <div id="pvUzeSummaryLine" style="margin-top:5px;font-size:12px;color:#888">
      × ${qty} шт = <b>${fmtNum(uze_total)} ${currSign}</b>
      &nbsp;|&nbsp; ємність: ${capacityKwh} кВт·год
      &nbsp;|&nbsp; <b>${perKwh} ${currSign}/кВт·год</b>
    </div>`;
}

function renderPvEquipment() {
  const { line_items, currency, equip_vat } = pvState;
  const currSign  = currency === 'EUR' ? '€' : '$';
  const vatColor  = equip_vat === 'з ПДВ' ? '#2e7d32' : '#e65100';
  const vatBadge  = `<span style="font-size:11px;font-weight:600;color:${vatColor};background:${equip_vat === 'з ПДВ' ? '#e8f5e9' : '#fff3e0'};padding:2px 7px;border-radius:10px;margin-left:6px">${equip_vat}</span>`;

  const rows = line_items.map((item, i) => `
    <div style="display:flex;align-items:center;gap:5px;padding:5px 0;border-bottom:1px solid #f0f0f0">
      <span style="width:18px;font-size:11px;color:#bbb;flex-shrink:0;text-align:right">${i + 1}</span>
      <input type="text" value="${item.name}"
        style="flex:1;padding:4px 6px;border:1px solid #e8e8e8;border-radius:6px;font-size:12px;min-width:0"
        oninput="pvState.line_items[${i}].name=this.value" />
      <input type="number" min="0.01" step="0.01" value="${item.qty}"
        style="width:46px;padding:4px;border:1px solid #e8e8e8;border-radius:6px;font-size:12px;text-align:center"
        oninput="onPvEquipQtyChange(${i},this.value)" />
      <input type="number" step="0.01" value="${item.price}"
        style="width:82px;padding:4px;border:1px solid #ddd;border-radius:6px;font-size:12px;text-align:right"
        oninput="onPvEquipPriceChange(${i},this.value)" />
      <span style="font-size:11px;color:#aaa;flex-shrink:0">${currSign}</span>
      <button onclick="removePvItem(${i})"
        style="padding:3px 6px;border-radius:6px;border:1px solid #ffcdd2;background:#fff;color:#e53935;cursor:pointer;font-size:11px;flex-shrink:0">✕</button>
    </div>`).join('');

  document.getElementById('pvEquipment').innerHTML = `<div style="margin-bottom:8px">${vatBadge}</div>` + rows + `
    <button onclick="addPvItem()"
      style="width:100%;margin-top:8px;padding:7px;border:1px dashed #ccc;border-radius:8px;background:#fafafa;cursor:pointer;font-size:13px;color:#555">
      + Додати позицію
    </button>`;
}

function renderPvTotals() {
  const { uze_price_per_unit, line_items, qty, currency } = pvState;
  const currSign    = currency === 'EUR' ? '€' : '$';
  const capacityKwh = (pvModel?.capacity_kwh || 0) * qty;
  const uze_total   = +(uze_price_per_unit * qty).toFixed(2);
  const equip_total = +line_items.reduce((s, e) => s + e.total, 0).toFixed(2);
  const total       = +(uze_total + equip_total).toFixed(2);
  const perKwh      = capacityKwh > 0 ? (total / capacityKwh).toFixed(2) : null;
  const rate        = currency === 'EUR'
    ? (window.UZE_CATALOG?.eur_rate || 50.88)
    : (window.UZE_CATALOG?.usd_rate || 43.81);
  const totalUAH    = Math.round(total * rate).toLocaleString('uk-UA');

  document.getElementById('pvTotals').innerHTML = `
    <div style="font-size:13px">
      <div style="display:flex;justify-content:space-between;padding:4px 0;color:#888">
        <span>УЗЕ (${qty} × ${fmtNum(uze_price_per_unit)} ${currSign})</span>
        <span>${fmtNum(uze_total)} ${currSign}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:4px 0;color:#888">
        <span>Обладнання та роботи (${pvState.equip_vat})</span>
        <span>${fmtNum(equip_total)} ${currSign}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 0 4px;border-top:2px solid #eee;margin-top:4px;font-weight:700;font-size:16px">
        <span>Загальна вартість</span>
        <span>${fmtNum(total)} ${currSign}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#888;padding-bottom:2px">
        <span>≈ UAH</span>
        <span>${totalUAH} грн</span>
      </div>
      ${perKwh ? `<div style="text-align:right;font-size:12px;color:#4caf50;font-weight:600">${perKwh} ${currSign}/кВт·год</div>` : ''}
    </div>`;
}

// ── Preview: оновлення при зміні ────────────────────────────────

function onPvUzePriceChange() {
  pvState.uze_price_per_unit = parseFloat(document.getElementById('pvUzeInput').value) || 0;
  updatePvTotals();
}

function onPvEquipQtyChange(i, val) {
  pvState.line_items[i].qty   = parseFloat(val) || 0;
  pvState.line_items[i].total = +(pvState.line_items[i].price * pvState.line_items[i].qty).toFixed(2);
  updatePvTotals();
}

function onPvEquipPriceChange(i, val) {
  pvState.line_items[i].price = parseFloat(val) || 0;
  pvState.line_items[i].total = +(pvState.line_items[i].price * pvState.line_items[i].qty).toFixed(2);
  updatePvTotals();
}

function updatePvTotals() {
  // оновлюємо рядок під ціною УЗЕ
  const { uze_price_per_unit, qty, currency, line_items } = pvState;
  const currSign    = currency === 'EUR' ? '€' : '$';
  const capacityKwh = (pvModel?.capacity_kwh || 0) * qty;
  const uze_total   = +(uze_price_per_unit * qty).toFixed(2);
  const equip_total = +line_items.reduce((s, e) => s + e.total, 0).toFixed(2);
  const total       = uze_total + equip_total;
  const perKwh      = capacityKwh > 0 ? (total / capacityKwh).toFixed(2) : '—';

  const summLine = document.getElementById('pvUzeSummaryLine');
  if (summLine) summLine.innerHTML = `
    × ${qty} шт = <b>${fmtNum(uze_total)} ${currSign}</b>
    &nbsp;|&nbsp; ємність: ${capacityKwh} кВт·год
    &nbsp;|&nbsp; <b>${perKwh} ${currSign}/кВт·год</b>`;

  renderPvTotals();
}

// ── Preview: додати / видалити рядок ───────────────────────────

function addPvItem() {
  // зберігаємо поточні значення полів перед re-render
  syncPvEquipFromDOM();
  pvState.line_items.push({ name: '', unit: 'компл.', qty: 1, price: 0, total: 0 });
  renderPvEquipment();
  renderPvTotals();
}

function removePvItem(i) {
  syncPvEquipFromDOM();
  pvState.line_items.splice(i, 1);
  renderPvEquipment();
  renderPvTotals();
}

function syncPvEquipFromDOM() {
  document.querySelectorAll('[oninput^="pvState.line_items"]').forEach(el => {
    const attr = el.getAttribute('oninput');
    const m = attr.match(/\[(\d+)\]\.name/);
    if (m) pvState.line_items[+m[1]].name = el.value;
  });
  // qty та price синхронізуються через onPvEquipQtyChange/onPvEquipPriceChange
}

// ── Відправити КП ──────────────────────────────────────────────

async function sendKP() {
  const btn   = document.getElementById('pvSendBtn');
  const errEl = document.getElementById('pvError');
  errEl.textContent = '';
  btn.disabled = true;
  btn.textContent = 'Відправляємо...';

  // Читаємо актуальні назви з DOM (у разі якщо oninput не спрацював)
  syncPvEquipFromDOM();

  const { uze_price_per_unit, line_items, qty, currency, uze_vat, equip_vat } = pvState;
  const currSign    = currency === 'EUR' ? '€' : '$';
  const capacityKwh = (pvModel?.capacity_kwh || 0) * qty;
  const uze_total   = +(uze_price_per_unit * qty).toFixed(2);
  const equip_total = +line_items.reduce((s, e) => s + e.total, 0).toFixed(2);
  const final_total = +(uze_total + equip_total).toFixed(2);

  // Перебудовуємо template_vars з відредагованих даних
  const todayStr = new Date().toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const tableRows = {};
  for (let i = 1; i <= 14; i++) {
    const eq = line_items[i - 1];
    tableRows[`{{r${i}_num}}`]   = eq ? String(i)          : '';
    tableRows[`{{r${i}_name}}`]  = eq ? eq.name            : '';
    tableRows[`{{r${i}_unit}}`]  = eq ? (eq.unit || 'шт.') : '';
    tableRows[`{{r${i}_qty}}`]   = eq ? String(eq.qty)     : '';
    tableRows[`{{r${i}_price}}`] = eq ? fmtNum(eq.price)   : '';
    tableRows[`{{r${i}_total}}`] = eq ? fmtNum(eq.total)   : '';
  }

  const templateVars = {
    ...pvCalc.template_vars,   // базові змінні з початкового розрахунку
    '{{uze_price_per_unit}}':  fmtNum(uze_price_per_unit),
    '{{uze_price_total}}':     fmtNum(uze_total),
    '{{project_total_price}}': fmtNum(final_total),
    '{{cost_build}}':          fmtNum(final_total),
    '{{total_price_no_vat}}':  equip_vat === 'без ПДВ' ? fmtNum(final_total) : fmtNum(final_total / 1.2),
    ...tableRows,
  };

  const uzeSettings = JSON.parse(localStorage.getItem('rayton_settings') || '{}');

  const payload = {
    ...pvFormData,
    type:          'uze',
    template_vars: templateVars,
    template_id:   pvCalc.template_id,
    tail_pages:    pvCalc.tail_pages,
    file_name:     pvCalc.file_name,
    doc_copy_name: pvCalc.doc_copy_name,
    final_total,
    line_items,
    uze_price_per_unit,
    uze_price_total:  uze_total,
    uze_drive_folder: uzeSettings.uze_drive_folder || '',
    ses_drive_folder: uzeSettings.ses_drive_folder || '',
  };

  try {
    await fetch(N8N_UZE_URL, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    btn.textContent = '✅ КП відправлено в Telegram';
    window.Telegram?.WebApp?.close?.();
  } catch {
    errEl.textContent = 'Помилка відправки. Перевірте інтернет.';
    btn.textContent   = '📤 Відправити КП';
    btn.disabled      = false;
  }
}

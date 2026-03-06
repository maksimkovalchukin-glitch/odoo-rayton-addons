/* ======================================================
   SETTINGS — Адмін-панель управління
====================================================== */

const ADMIN_PASSWORD    = '12345';
const STORAGE_KEY       = 'rayton_managers';
const SETTINGS_STORAGE  = 'rayton_settings';

const MANAGERS_URL = 'https://n8n.rayton.net/webhook/managers';
const SETTINGS_URL = 'https://n8n.rayton.net/webhook/settings';

let managers = [];

const DEFAULT_MANAGERS = [
  { name: 'Петров Дмитро',        phone: '+38 (063) 847-49-83', email: 'd.petrov@rayton.com.ua', telegram: '', active: true },
  { name: 'Тубіш Микола',         phone: '+38 (067) 197-57-23', email: 'mt@rayton.com.ua',        telegram: '', active: true },
  { name: 'Сидоров Максим',       phone: '+38 (063) 847-49-76', email: 'ms@rayton.com.ua',        telegram: '', active: true },
  { name: 'Достовалов Олександр', phone: '+38 (063) 847-49-77', email: 'od@rayton.com.ua',        telegram: '', active: true },
  { name: 'Стоцький Віталій',     phone: '+38 (067) 349-79-33', email: 'vs@rayton.com.ua',        telegram: '', active: true },
  { name: 'Павлов Дмитро',        phone: '+38 (063) 847-49-76', email: 'dp@rayton.com.ua',        telegram: '', active: true },
  { name: 'Лисенко Юрій',         phone: '+38 (063) 847-49-82', email: 'yl@rayton.com.ua',        telegram: '', active: true },
];

document.addEventListener('DOMContentLoaded', () => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.expand();
    tg.ready();
    tg.BackButton.show();
    tg.BackButton.onClick(() => { window.location.href = 'index.html'; });
  }

  const loginBtn      = document.getElementById('loginBtn');
  const passwordInput = document.getElementById('passwordInput');

  loginBtn.addEventListener('click', tryLogin);
  passwordInput.addEventListener('keydown', e => { if (e.key === 'Enter') tryLogin(); });

  document.getElementById('addBtn').addEventListener('click', addManager);
  document.getElementById('saveBtn').addEventListener('click', saveManagers);
  document.getElementById('saveTplBtn').addEventListener('click', saveTemplates);
  document.getElementById('saveCatalogBtn').addEventListener('click', saveSESCatalog);
  document.getElementById('saveUZEBtn').addEventListener('click', saveUZECatalog);
});

// ── Логін ──────────────────────────────────────────────────────

function tryLogin() {
  const input = document.getElementById('passwordInput');
  if (input.value !== ADMIN_PASSWORD) {
    document.getElementById('passwordError').style.display = '';
    return;
  }
  document.getElementById('passwordScreen').style.display = 'none';
  document.getElementById('adminPanel').style.display     = '';
  fetchNBURates();
  loadManagers();
  loadTemplates();
  loadEquipment();
  loadUZECatalog();
}

// ── Курси валют ────────────────────────────────────────────────

const NBU_API = 'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json';
const RATES_KEY = 'rayton_rates';

async function fetchNBURates() {
  const btn    = document.getElementById('nbuBtn');
  const status = document.getElementById('rateStatus');
  if (btn) btn.disabled = true;
  if (status) status.textContent = 'Завантаження...';
  try {
    const res  = await fetch(NBU_API, { cache: 'no-store' });
    const data = await res.json();
    const usd  = data.find(r => r.cc === 'USD')?.rate;
    const eur  = data.find(r => r.cc === 'EUR')?.rate;
    if (usd) document.getElementById('rateUSD').value = usd.toFixed(2);
    if (eur) document.getElementById('rateEUR').value = eur.toFixed(2);
    const date = data[0]?.exchangedate || '';
    if (status) { status.textContent = `✅ Оновлено ${date}`; status.style.color = '#4caf50'; }
    localStorage.setItem(RATES_KEY, JSON.stringify({ usd_rate: usd, eur_rate: eur, date }));
  } catch {
    // fallback to cached
    const cached = localStorage.getItem(RATES_KEY);
    if (cached) {
      const { usd_rate, eur_rate, date } = JSON.parse(cached);
      if (usd_rate) document.getElementById('rateUSD').value = usd_rate.toFixed(2);
      if (eur_rate) document.getElementById('rateEUR').value = eur_rate.toFixed(2);
      if (status) { status.textContent = `⚠️ Кеш ${date}`; status.style.color = '#f57c00'; }
    } else {
      // використовуємо сталі значення з каталогу
      const sesCatalog = window.SES_CATALOG || window.CATALOG;
      const uzeCatalog = window.UZE_CATALOG;
      const usd = sesCatalog?.usd_rate || uzeCatalog?.usd_rate;
      const eur = sesCatalog?.eur_rate || uzeCatalog?.eur_rate;
      if (usd) document.getElementById('rateUSD').value = (+usd).toFixed(2);
      if (eur) document.getElementById('rateEUR').value = (+eur).toFixed(2);
      if (status) { status.textContent = `⚠️ НБУ недоступний — використано збережений курс`; status.style.color = '#f57c00'; }
    }
  }
  if (btn) btn.disabled = false;
}

function getSharedRates() {
  return {
    usd_rate: parseFloat(document.getElementById('rateUSD')?.value) || 43.8059,
    eur_rate: parseFloat(document.getElementById('rateEUR')?.value) || 50.8781,
  };
}

// ── Таби ───────────────────────────────────────────────────────

function switchTab(tab) {
  ['managers','templates','catalog','uze'].forEach(t => {
    document.getElementById(`tabContent${t.charAt(0).toUpperCase()+t.slice(1)}`).style.display = t === tab ? '' : 'none';
    const btn = document.getElementById(`tab${t.charAt(0).toUpperCase()+t.slice(1)}`);
    if (btn) btn.className = t === tab ? 'active' : '';
  });
}

// Fix tab ids mapping
function switchTab(tab) {
  const tabs = { managers: 'tabContentManagers', templates: 'tabContentTemplates', catalog: 'tabContentCatalog', uze: 'tabContentUZE' };
  const btns = { managers: 'tabManagers', templates: 'tabTemplates', catalog: 'tabCatalog', uze: 'tabUZE' };
  Object.keys(tabs).forEach(t => {
    document.getElementById(tabs[t]).style.display = t === tab ? '' : 'none';
    const btn = document.getElementById(btns[t]);
    if (btn) btn.className = t === tab ? 'active' : '';
  });
}

// ── Менеджери ──────────────────────────────────────────────────

async function loadManagers() {
  try {
    const res  = await fetch(MANAGERS_URL, { cache: 'no-store' });
    const data = await res.json();
    managers   = data.managers || [];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(managers));
  } catch {
    const stored = localStorage.getItem(STORAGE_KEY);
    managers = stored ? JSON.parse(stored) : [];
  }
  if (!managers.length) managers = DEFAULT_MANAGERS;
  renderList();
}

function renderList() {
  const list = document.getElementById('managerList');
  if (!managers.length) {
    list.innerHTML = '<div style="text-align:center;padding:24px;color:#888">Список порожній</div>';
    return;
  }
  list.innerHTML = managers.map((m, i) => `
    <div style="background:#fff;border:1px solid #e8e8e8;border-radius:12px;padding:12px 14px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div style="font-weight:700;font-size:15px">${m.name}</div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button onclick="toggleManager(${i})"
            style="padding:4px 10px;border-radius:8px;border:1px solid #e0e0e0;background:${m.active ? '#e8f5e9' : '#fce4ec'};cursor:pointer;font-size:12px">
            ${m.active ? '✅ Актив.' : '🚫 Вимкн.'}
          </button>
          <button onclick="editManager(${i})"
            style="padding:4px 8px;border-radius:8px;border:1px solid #e0e0e0;background:#fff;cursor:pointer;font-size:12px">✏️</button>
          <button onclick="removeManager(${i})"
            style="padding:4px 8px;border-radius:8px;border:1px solid #ffcdd2;background:#fff;color:#e53935;cursor:pointer;font-size:12px">🗑</button>
        </div>
      </div>
      <div style="margin-top:6px;font-size:13px;color:#555;display:flex;flex-wrap:wrap;gap:4px 16px">
        <span>📞 ${m.phone || '—'}</span>
        <span>📧 ${m.email || '—'}</span>
        ${m.telegram ? `<span>✈️ @${m.telegram}</span>` : ''}
      </div>
    </div>`).join('');
}

function toggleManager(i) { managers[i].active = !managers[i].active; renderList(); }
function removeManager(i)  { managers.splice(i, 1); renderList(); }

let editingIndex = null;

function editManager(i) {
  const m = managers[i];
  editingIndex = i;
  document.getElementById('addName').value     = m.name;
  document.getElementById('addPhone').value    = m.phone    || '';
  document.getElementById('addEmail').value    = m.email    || '';
  document.getElementById('addTelegram').value = m.telegram || '';
  document.getElementById('addBtn').textContent = 'Зберегти зміни';
  document.querySelector('.divider').scrollIntoView({ behavior: 'smooth' });
}

function addManager() {
  const name     = document.getElementById('addName').value.trim();
  const phone    = document.getElementById('addPhone').value.trim();
  const email    = document.getElementById('addEmail').value.trim();
  const telegram = document.getElementById('addTelegram').value.trim().replace(/^@/, '');
  const errEl    = document.getElementById('addError');
  if (!name) { errEl.style.display = ''; return; }
  errEl.style.display = 'none';

  if (editingIndex !== null) {
    managers[editingIndex] = { ...managers[editingIndex], name, phone, email, telegram };
    editingIndex = null;
    document.getElementById('addBtn').textContent = 'Додати';
  } else {
    managers.push({ name, phone, email, telegram, active: true });
  }
  renderList();
  ['addName','addPhone','addEmail','addTelegram'].forEach(id => document.getElementById(id).value = '');
}

async function saveManagers() {
  const btn    = document.getElementById('saveBtn');
  const status = document.getElementById('saveStatus');
  btn.disabled = true;
  status.textContent = 'Зберігаємо...';
  localStorage.setItem(STORAGE_KEY, JSON.stringify(managers));
  try {
    await fetch(MANAGERS_URL, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ managers }) });
    status.textContent = '✅ Збережено';
    status.style.color = 'green';
  } catch {
    status.textContent = '✅ Збережено локально';
    status.style.color = '#888';
  }
  btn.disabled = false;
}

// ── Шаблони ────────────────────────────────────────────────────

const TEMPLATE_FIELD_MAP = {
  tplSector1:        'ses_tpl_sector1',
  tplSector2:        'ses_tpl_sector2',
  tplSector3:        'ses_tpl_sector3',
  tplSector4:        'ses_tpl_sector4',
  tplSector5:        'ses_tpl_sector5',
  tplSector6:        'ses_tpl_sector6',
  tplDriveFolder:    'ses_drive_folder',
  uzeDriveFolder:    'uze_drive_folder',
  sesCreditPageNum:  'ses_credit_page_num',
  sesVizPageNum:     'ses_viz_page_num',
};

async function loadTemplates() {
  let settings = {};
  try {
    const res  = await fetch(SETTINGS_URL, { cache: 'no-store' });
    const data = await res.json();
    settings   = data.settings || {};
    localStorage.setItem(SETTINGS_STORAGE, JSON.stringify(settings));
  } catch {
    const stored = localStorage.getItem(SETTINGS_STORAGE);
    if (stored) settings = JSON.parse(stored);
  }
  Object.entries(TEMPLATE_FIELD_MAP).forEach(([elId, key]) => {
    const el = document.getElementById(elId);
    if (el && settings[key]) el.value = settings[key];
  });
}

function readTemplateFields() {
  const out = {};
  Object.entries(TEMPLATE_FIELD_MAP).forEach(([elId, key]) => {
    const el = document.getElementById(elId);
    if (el) out[key] = el.value.trim();
  });
  return out;
}

async function saveTemplates() {
  const btn    = document.getElementById('saveTplBtn');
  const status = document.getElementById('saveTplStatus');
  btn.disabled = true;
  status.textContent = 'Зберігаємо...';
  const settings = readTemplateFields();
  localStorage.setItem(SETTINGS_STORAGE, JSON.stringify(settings));
  try {
    await fetch(SETTINGS_URL, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ settings }) });
    status.textContent = '✅ Збережено';
    status.style.color = 'green';
  } catch {
    status.textContent = '✅ Збережено локально';
    status.style.color = '#888';
  }
  btn.disabled = false;
}

// ── Каталог СЕС ────────────────────────────────────────────────

// staticMarkup: true — адмін змінює вручну
// staticMarkup: false — коефіцієнт розраховується рушієм динамічно від ціни/кВт
const CATALOG_SECTIONS = [
  { key: 'panels',             listId: 'panelsList',           unit: '$/шт',    staticMarkup: true  },
  { key: 'inverters',          listId: 'invertersList',        unit: '$/шт',    staticMarkup: true  },
  { key: 'monitoring',         listId: 'monitoringList',       unit: '$/шт',    staticMarkup: true  },
  { key: 'power_control',      listId: 'powerControlList',     unit: '$/компл', staticMarkup: true  },
  { key: 'mounting_types',     listId: 'mountingTypesList',    unit: '$/шт',    staticMarkup: false, markupRange: [1.0, 7.1875] },
  { key: 'materials_dc_lt100', listId: 'materialsDcLt100List', unit: '$/кВт',   staticMarkup: false, markupRange: [1.0, 6.75]   },
  { key: 'materials_dc_gt100', listId: 'materialsDcGt100List', unit: '$/кВт',   staticMarkup: false, markupRange: [1.0, 6.75]   },
  { key: 'materials_ac_lt100', listId: 'materialsAcLt100List', unit: '$/кВт',   staticMarkup: false, markupRange: [1.0, 6.75]   },
  { key: 'materials_ac_gt100', listId: 'materialsAcGt100List', unit: '$/кВт',   staticMarkup: false, markupRange: [1.0, 6.75]   },
  { key: 'montage',            listId: 'montageList',          unit: '$/кВт',   staticMarkup: false, markupRange: [1.0, 3.0188] },
  { key: 'tech',               listId: 'techList',             unit: '$/об',    staticMarkup: false, markupRange: [1.0, 3.0188] },
  { key: 'delivery',           listId: 'deliveryList',         unit: '$/об',    staticMarkup: false, markupRange: [1.0, 3.0188] },
];

async function loadEquipment() {
  await window.CatalogAPI?.loadSES?.();
  renderCatalogUI(window.SES_CATALOG || window.CATALOG);
}

function renderCatalogSection(key) {
  const sec     = CATALOG_SECTIONS.find(s => s.key === key);
  if (!sec) return;
  const catalog = window.SES_CATALOG || window.CATALOG;
  if (!catalog) return;
  const el = document.getElementById(sec.listId);
  if (!el) return;

  const items  = catalog[key] || [];
  const markup = items[0]?.markup || '';

  const rangeText = sec.markupRange
    ? `від ${sec.markupRange[0]} до ${sec.markupRange[1]}`
    : 'динамічно';
  const markupRow = sec.staticMarkup ? `
    <div style="display:flex;align-items:center;gap:8px;padding:6px 0 8px;border-bottom:2px solid #e8e8e8;margin-bottom:4px">
      <span style="flex:1;font-size:12px;color:#888">Стала націнка ×</span>
      <input type="number" step="0.001" value="${markup}"
        style="width:70px;padding:5px;border:1px solid #FFC400;border-radius:6px;font-size:13px;text-align:right;font-weight:600"
        data-cat-markup="${key}" />
      <span style="font-size:11px;color:#888">×</span>
    </div>` :
    `<div style="font-size:11px;color:#aaa;padding:4px 0 8px;border-bottom:2px solid #e8e8e8;margin-bottom:4px">
      Націнка розраховується динамічно (коефіцієнт ${rangeText})
    </div>`;

  const rows = items.map((item, i) => `
    <div style="display:flex;align-items:center;gap:6px;padding:6px 0;border-bottom:1px solid #f0f0f0">
      <input type="text" value="${item.name}"
        style="flex:1;padding:5px 7px;border:1px solid #e8e8e8;border-radius:6px;font-size:13px;min-width:0"
        data-cat-name="${key}" data-idx="${i}" />
      <input type="number" step="0.01" value="${item.buy_usd || ''}"
        style="width:80px;padding:5px;border:1px solid #ddd;border-radius:6px;font-size:13px;text-align:right"
        data-cat-key="${key}" data-idx="${i}" placeholder="ціна" />
      <span style="font-size:11px;color:#888;flex-shrink:0">${sec.unit}</span>
      <button onclick="removeCatalogItem('${key}',${i})"
        style="padding:3px 7px;border-radius:6px;border:1px solid #ffcdd2;background:#fff;color:#e53935;cursor:pointer;font-size:12px;flex-shrink:0">✕</button>
    </div>`).join('');

  const addBtn = `
    <button onclick="addCatalogItem('${key}')"
      style="width:100%;margin-top:8px;padding:7px;border:1px dashed #ccc;border-radius:8px;background:#fafafa;cursor:pointer;font-size:13px;color:#555">
      + Додати рядок
    </button>`;

  el.innerHTML = markupRow + rows + addBtn;
}

function renderCatalogUI(catalog) {
  if (!catalog) return;
  // prefill shared rate fields only if not already set (NBU fetch may have filled them)
  const rateEUR = document.getElementById('rateEUR');
  const rateUSD = document.getElementById('rateUSD');
  if (rateEUR && !rateEUR.value && catalog.eur_rate) rateEUR.value = catalog.eur_rate;
  if (rateUSD && !rateUSD.value && catalog.usd_rate) rateUSD.value = catalog.usd_rate;
  CATALOG_SECTIONS.forEach(({ key }) => renderCatalogSection(key));
}

function addCatalogItem(key) {
  const catalog = window.SES_CATALOG || window.CATALOG;
  if (!catalog[key]) catalog[key] = [];
  const sec = CATALOG_SECTIONS.find(s => s.key === key);
  const defaultMarkup = catalog[key][0]?.markup || (sec?.staticMarkup ? 1.15 : 1.7348);
  catalog[key].push({ name: '', unit: sec?.unit?.replace('$/', '') || 'шт.', buy_usd: 0, markup: defaultMarkup, sell_usd: 0 });
  renderCatalogSection(key);
}

function removeCatalogItem(key, idx) {
  const catalog = window.SES_CATALOG || window.CATALOG;
  if (!catalog[key]) return;
  catalog[key].splice(idx, 1);
  renderCatalogSection(key);
}

function readCatalogUI() {
  const catalog = JSON.parse(JSON.stringify(window.SES_CATALOG || window.CATALOG || {}));
  const { usd_rate, eur_rate } = getSharedRates();
  catalog.usd_rate = usd_rate;
  catalog.eur_rate = eur_rate;

  const markups = {};
  document.querySelectorAll('[data-cat-markup]').forEach(el => {
    const val = parseFloat(el.value);
    if (!isNaN(val)) markups[el.dataset.catMarkup] = val;
  });

  // Читаємо назви
  document.querySelectorAll('[data-cat-name]').forEach(el => {
    const key = el.dataset.catName;
    const idx = parseInt(el.dataset.idx);
    if (catalog[key]?.[idx]) catalog[key][idx].name = el.value.trim();
  });

  // Читаємо ціни закупівлі
  document.querySelectorAll('[data-cat-key]').forEach(el => {
    const key = el.dataset.catKey;
    const idx = parseInt(el.dataset.idx);
    const val = parseFloat(el.value);
    if (isNaN(val) || !catalog[key]?.[idx]) return;
    const markup = markups[key] ?? catalog[key][idx].markup;
    catalog[key][idx].buy_usd  = val;
    catalog[key][idx].markup   = markup;
    catalog[key][idx].sell_usd = +(val * markup).toFixed(4);
  });

  return catalog;
}

async function saveSESCatalog() {
  const btn    = document.getElementById('saveCatalogBtn');
  const status = document.getElementById('saveCatalogStatus');
  btn.disabled = true;
  status.textContent = 'Зберігаємо...';
  try {
    await window.CatalogAPI.saveSES(readCatalogUI());
    status.textContent = '✅ Збережено';
    status.style.color = 'green';
  } catch {
    status.textContent = '✅ Збережено локально';
    status.style.color = '#888';
  }
  btn.disabled = false;
}

// ── Каталог УЗЕ ────────────────────────────────────────────────

async function loadUZECatalog() {
  await window.CatalogAPI?.loadUZE?.();
  renderUZECatalogUI(window.UZE_CATALOG);
}

function uzeCardBorder(filled) {
  return filled ? '2px solid #4caf50' : '2px solid #e53935';
}

function uzeCardHeaderBg(filled) {
  return filled ? '#f1f8f1' : '#fff8f8';
}

function onUzePriceInput(input, mi) {
  const card   = document.getElementById(`uze-card-${mi}`);
  const header = document.getElementById(`uze-header-${mi}`);
  const badge  = document.getElementById(`uze-badge-${mi}`);
  // check if any price field for this model is > 0
  const filled = Array.from(document.querySelectorAll(`[data-uze-mi="${mi}"][data-uze-field="uze_sell_novat_usd"]`))
    .some(el => parseFloat(el.value) > 0);
  if (card)   card.style.border       = uzeCardBorder(filled);
  if (header) header.style.background = uzeCardHeaderBg(filled);
  if (badge)  { badge.textContent = filled ? '✅' : '❌'; badge.style.color = filled ? '#4caf50' : '#e53935'; }
}

function renderUZECatalogUI(catalog) {
  const container = document.getElementById('uzeModelsList');
  if (!container || !catalog?.models) return;

  container.innerHTML = (catalog.models || []).map((model, mi) => {
    const hasPrice = model.scenarios?.some(sc => sc.uze_price?.sell_novat_usd > 0);
    const filled = hasPrice;

    const scaleTag = model.unlimited
      ? `<span style="font-size:11px;background:#e3f2fd;color:#1565c0;border-radius:6px;padding:2px 7px;flex-shrink:0">∞ масштабується</span>`
      : `<span style="font-size:11px;background:#f3e5f5;color:#6a1b9a;border-radius:6px;padding:2px 7px;flex-shrink:0">макс. ${model.max_qty || '?'} шт</span>`;

    const scenariosHtml = model.scenarios.map((sc, si) => {
      const qtyLabel = model.unlimited
        ? `<div style="font-size:12px;font-weight:600;color:#555;margin-bottom:6px">×${sc.qty} (базовий)</div>`
        : `<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
            <span style="font-size:12px;font-weight:600;color:#555">К-ть:</span>
            <input type="number" min="1" value="${sc.qty}"
              style="width:60px;padding:3px 6px;border:1px solid #ddd;border-radius:6px;font-size:12px;text-align:center"
              data-uze-mi="${mi}" data-uze-si="${si}" data-uze-field="sc_qty" />
          </div>`;

      const equipmentRows = (sc.equipment || []).map((eq, ei) => `
        <div style="display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid #f5f5f5">
          <input type="text" value="${eq.name}"
            style="flex:1;padding:4px 6px;border:1px solid #e8e8e8;border-radius:6px;font-size:12px;min-width:0"
            data-uze-mi="${mi}" data-uze-si="${si}" data-uze-ei="${ei}" data-uze-field="eq_name" />
          <input type="number" min="1" value="${eq.qty}"
            style="width:44px;padding:4px;border:1px solid #e8e8e8;border-radius:6px;font-size:12px;text-align:center"
            data-uze-mi="${mi}" data-uze-si="${si}" data-uze-ei="${ei}" data-uze-field="eq_qty" />
          <input type="number" step="0.01" value="${eq.sell_novat_usd || ''}"
            style="width:80px;padding:4px;border:1px solid #ddd;border-radius:6px;font-size:12px;text-align:right"
            data-uze-mi="${mi}" data-uze-si="${si}" data-uze-ei="${ei}" data-uze-field="eq_sell_novat_usd"
            placeholder="$/шт" />
          <button onclick="removeUzeEquipment(${mi},${si},${ei})"
            style="padding:3px 6px;border-radius:6px;border:1px solid #ffcdd2;background:#fff;color:#e53935;cursor:pointer;font-size:11px;flex-shrink:0">✕</button>
        </div>`).join('');

      return `
        <div style="padding:8px 0;border-top:1px solid #eee">
          ${qtyLabel}
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span style="font-size:12px;color:#444;flex:1">Ціна УЗЕ без ПДВ ($)</span>
            <input type="number" step="0.01" value="${sc.uze_price?.sell_novat_usd || ''}"
              style="width:100px;padding:5px;border:1px solid #FFC400;border-radius:6px;font-size:13px;text-align:right;font-weight:600"
              data-uze-mi="${mi}" data-uze-si="${si}" data-uze-field="uze_sell_novat_usd"
              oninput="onUzePriceInput(this,${mi})" />
          </div>
          <div style="font-size:11px;font-weight:600;color:#888;margin:4px 0">Матеріали та роботи:</div>
          ${equipmentRows}
          <button onclick="addUzeEquipment(${mi},${si})"
            style="width:100%;margin-top:6px;padding:5px;border:1px dashed #ccc;border-radius:7px;background:#fafafa;cursor:pointer;font-size:12px;color:#555">
            + Додати рядок обладнання
          </button>
        </div>`;
    }).join('');

    return `
      <div class="model-card" id="uze-card-${mi}" style="border:${uzeCardBorder(filled)}">
        <div class="model-header" id="uze-header-${mi}" onclick="toggleModel(${mi})" style="background:${uzeCardHeaderBg(filled)}">
          <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:0">
            <span style="font-size:13px;font-weight:600">${model.name}</span>
            ${scaleTag}
          </div>
          <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;margin-left:8px">
            <span id="uze-badge-${mi}" style="font-size:16px;color:${filled ? '#4caf50' : '#e53935'}">${filled ? '✅' : '❌'}</span>
            <button onclick="event.stopPropagation();removeUzeModel(${mi})"
              style="padding:3px 7px;border-radius:7px;border:1px solid #ffcdd2;background:#fff;color:#e53935;cursor:pointer;font-size:12px">🗑</button>
            <span id="arrow-${mi}" style="font-size:12px;color:#888">▼</span>
          </div>
        </div>
        <div class="model-body" id="model-body-${mi}" style="background:#fff">
          <div class="field">
            <label>Google Doc Template ID</label>
            <input type="text" placeholder="Doc ID" value="${model.template_id || ''}"
              data-uze-mi="${mi}" data-uze-field="template_id"
              style="width:100%;padding:7px;border:1px solid #ddd;border-radius:6px;font-size:12px;box-sizing:border-box" />
          </div>
          <div class="field" style="margin-top:6px">
            <label>Tail pages (хвостові сторінки)</label>
            <input type="number" min="1" max="20" value="${model.tail_pages || 5}"
              data-uze-mi="${mi}" data-uze-field="tail_pages"
              style="width:80px;padding:7px;border:1px solid #ddd;border-radius:6px;font-size:13px" />
          </div>
          ${scenariosHtml}
        </div>
      </div>`;
  }).join('');
}

function toggleModel(mi) {
  const body  = document.getElementById(`model-body-${mi}`);
  const arrow = document.getElementById(`arrow-${mi}`);
  const open  = body.classList.toggle('open');
  if (arrow) arrow.textContent = open ? '▲' : '▼';
}

function syncUzeAndRender(fn) {
  const catalog = readUZECatalogUI();
  window.UZE_CATALOG = catalog;
  fn(catalog);
  renderUZECatalogUI(catalog);
}

function addUzeEquipment(mi, si) {
  syncUzeAndRender(catalog => {
    if (!catalog.models[mi]?.scenarios[si]) return;
    catalog.models[mi].scenarios[si].equipment = catalog.models[mi].scenarios[si].equipment || [];
    catalog.models[mi].scenarios[si].equipment.push({ name: '', unit: 'компл.', qty: 1, sell_novat_usd: 0, sell_vat_usd: 0, sell_novat_eur: 0, sell_vat_eur: 0 });
  });
}

function removeUzeEquipment(mi, si, ei) {
  syncUzeAndRender(catalog => {
    catalog.models[mi]?.scenarios[si]?.equipment?.splice(ei, 1);
  });
}

function removeUzeModel(mi) {
  syncUzeAndRender(catalog => {
    catalog.models.splice(mi, 1);
  });
}

function addUzeModel() {
  syncUzeAndRender(catalog => {
    catalog.models = catalog.models || [];
    catalog.models.push({
      name: 'Нова модель УЗЕ',
      description: '',
      power_kw: 0,
      capacity_kwh: 0,
      unlimited: false,
      max_qty: 5,
      template_id: '',
      tail_pages: 5,
      scenarios: [{ qty: 1, uze_price: { sell_novat_usd: 0, sell_vat_usd: 0, sell_novat_eur: 0, sell_vat_eur: 0 }, equipment: [] }],
    });
  });
}

function calcUzePrices(novat_usd, usd_rate, eur_rate) {
  const vat_usd    = +(novat_usd * 1.2).toFixed(4);
  const novat_eur  = +(novat_usd * usd_rate / eur_rate).toFixed(4);
  const vat_eur    = +(novat_eur * 1.2).toFixed(4);
  return { sell_novat_usd: novat_usd, sell_vat_usd: vat_usd, sell_novat_eur: novat_eur, sell_vat_eur: vat_eur };
}

function readUZECatalogUI() {
  const catalog  = JSON.parse(JSON.stringify(window.UZE_CATALOG || {}));
  if (!catalog.models) return catalog;
  const { usd_rate, eur_rate } = getSharedRates();
  catalog.usd_rate = usd_rate;
  catalog.eur_rate = eur_rate;

  document.querySelectorAll('[data-uze-mi]').forEach(el => {
    const mi    = parseInt(el.dataset.uzeMi);
    const field = el.dataset.uzeField;
    const val   = el.value.trim();
    if (!catalog.models[mi]) return;

    if (field === 'template_id') {
      catalog.models[mi].template_id = val;
    } else if (field === 'tail_pages') {
      catalog.models[mi].tail_pages = parseInt(val) || 5;
    } else if (field === 'uze_sell_novat_usd') {
      const si = parseInt(el.dataset.uzeSi);
      const numVal = parseFloat(val);
      if (!isNaN(si) && !isNaN(numVal) && catalog.models[mi].scenarios[si]) {
        catalog.models[mi].scenarios[si].uze_price = {
          ...catalog.models[mi].scenarios[si].uze_price,
          ...calcUzePrices(numVal, usd_rate, eur_rate),
        };
      }
    } else if (field === 'sc_qty') {
      const si = parseInt(el.dataset.uzeSi);
      if (!isNaN(si) && catalog.models[mi].scenarios[si])
        catalog.models[mi].scenarios[si].qty = parseInt(val) || 1;
    } else if (field === 'eq_name') {
      const si = parseInt(el.dataset.uzeSi);
      const ei = parseInt(el.dataset.uzeEi);
      if (!isNaN(si) && !isNaN(ei) && catalog.models[mi].scenarios[si]?.equipment[ei])
        catalog.models[mi].scenarios[si].equipment[ei].name = val;
    } else if (field === 'eq_qty') {
      const si = parseInt(el.dataset.uzeSi);
      const ei = parseInt(el.dataset.uzeEi);
      if (!isNaN(si) && !isNaN(ei) && catalog.models[mi].scenarios[si]?.equipment[ei])
        catalog.models[mi].scenarios[si].equipment[ei].qty = parseInt(val) || 1;
    } else if (field === 'eq_sell_novat_usd') {
      const si = parseInt(el.dataset.uzeSi);
      const ei = parseInt(el.dataset.uzeEi);
      const numVal = parseFloat(val);
      if (!isNaN(si) && !isNaN(ei) && !isNaN(numVal) && catalog.models[mi].scenarios[si]?.equipment[ei]) {
        const eq = catalog.models[mi].scenarios[si].equipment[ei];
        Object.assign(eq, calcUzePrices(numVal, usd_rate, eur_rate));
      }
    }
  });

  return catalog;
}

async function saveUZECatalog() {
  const btn    = document.getElementById('saveUZEBtn');
  const status = document.getElementById('saveUZEStatus');
  btn.disabled = true;
  status.textContent = 'Зберігаємо...';
  try {
    await window.CatalogAPI.saveUZE(readUZECatalogUI());
    status.textContent = '✅ Збережено';
    status.style.color = 'green';
  } catch {
    status.textContent = '✅ Збережено локально';
    status.style.color = '#888';
  }
  btn.disabled = false;
}

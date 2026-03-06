/* ======================================================
   SETTINGS — Адмін-панель управління менеджерами і шаблонами
====================================================== */

const ADMIN_PASSWORD = '12345';
const STORAGE_KEY = 'rayton_managers';
const SETTINGS_STORAGE_KEY = 'rayton_settings';

const MANAGERS_GET_URL  = 'https://n8n.rayton.net/webhook/ses-managers';
const MANAGERS_POST_URL = 'https://n8n.rayton.net/webhook/ses-managers';
const SETTINGS_GET_URL  = 'https://n8n.rayton.net/webhook/ses-settings';
const SETTINGS_POST_URL = 'https://n8n.rayton.net/webhook/ses-settings';

let managers = [];

document.addEventListener('DOMContentLoaded', () => {

  const passwordScreen = document.getElementById('passwordScreen');
  const adminPanel     = document.getElementById('adminPanel');
  const passwordInput  = document.getElementById('passwordInput');
  const passwordError  = document.getElementById('passwordError');
  const loginBtn       = document.getElementById('loginBtn');
  const saveBtn        = document.getElementById('saveBtn');
  const saveStatus     = document.getElementById('saveStatus');

  // ── Логін ──────────────────────────────────────────

  loginBtn.addEventListener('click', tryLogin);
  passwordInput.addEventListener('keydown', e => { if (e.key === 'Enter') tryLogin(); });

  function tryLogin() {
    if (passwordInput.value === ADMIN_PASSWORD) {
      passwordScreen.style.display = 'none';
      adminPanel.style.display = '';
      loadManagers();
      loadTemplates();
    } else {
      passwordError.style.display = '';
    }
  }

  // ── Зберегти менеджерів ────────────────────────────

  saveBtn.addEventListener('click', async () => {
    saveBtn.disabled = true;
    saveStatus.textContent = 'Зберігаємо...';
    saveStatus.style.color = '#888';

    localStorage.setItem(STORAGE_KEY, JSON.stringify(managers));

    try {
      await fetch(MANAGERS_POST_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ managers })
      });
      saveStatus.textContent = '✅ Збережено';
      saveStatus.style.color = 'green';
    } catch {
      saveStatus.textContent = '✅ Збережено локально (n8n недоступний)';
      saveStatus.style.color = '#888';
    }

    saveBtn.disabled = false;
  });

  // ── Зберегти шаблони ────────────────────────────────

  document.getElementById('saveTplBtn').addEventListener('click', async () => {
    const btn    = document.getElementById('saveTplBtn');
    const status = document.getElementById('saveTplStatus');
    btn.disabled = true;
    status.textContent = 'Зберігаємо...';
    status.style.color = '#888';

    const settings = readTemplateFields();
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));

    try {
      await fetch(SETTINGS_POST_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings })
      });
      status.textContent = '✅ Збережено';
      status.style.color = 'green';
    } catch {
      status.textContent = '✅ Збережено локально (n8n недоступний)';
      status.style.color = '#888';
    }

    btn.disabled = false;
  });

  // ── Додати менеджера ────────────────────────────────

  document.getElementById('addBtn').addEventListener('click', () => {
    const name     = document.getElementById('addName').value.trim();
    const phone    = document.getElementById('addPhone').value.trim();
    const email    = document.getElementById('addEmail').value.trim();
    const telegram = document.getElementById('addTelegram').value.trim().replace(/^@/, '');

    if (!name || !telegram) {
      document.getElementById('addError').style.display = '';
      return;
    }
    document.getElementById('addError').style.display = 'none';

    managers.push({ name, phone, email, telegram, active: true });
    renderList();
    clearAddForm();
  });

});

// ── Завантажити менеджерів ──────────────────────────

async function loadManagers() {
  try {
    const res = await fetch(MANAGERS_GET_URL, { cache: 'no-store' });
    const data = await res.json();
    managers = data.managers || [];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(managers));
  } catch {
    const stored = localStorage.getItem(STORAGE_KEY);
    managers = stored ? JSON.parse(stored) : [];
  }
  renderList();
}

// ── Рендер списку ───────────────────────────────────

function renderList() {
  const list = document.getElementById('managerList');

  if (managers.length === 0) {
    list.innerHTML = '<div style="text-align:center;padding:24px;color:#888">Список порожній</div>';
    return;
  }

  list.innerHTML = managers.map((m, i) => `
    <div class="card form-card" style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">

        <div style="flex:1;min-width:0">
          <div style="font-weight:600;margin-bottom:6px">${m.name}</div>
          <div style="font-size:13px;color:#555;margin-bottom:2px">📞 ${m.phone || '<span style="color:#bbb">—</span>'}</div>
          <div style="font-size:13px;color:#555;margin-bottom:2px">📧 ${m.email || '<span style="color:#bbb">—</span>'}</div>
          <div style="font-size:13px;color:#555">✈️ @${m.telegram}</div>
        </div>

        <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">
          <button
            onclick="toggleManager(${i})"
            style="padding:5px 10px;border-radius:8px;border:1px solid #e0e0e0;background:${m.active ? '#e8f5e9' : '#fce4ec'};cursor:pointer;font-size:12px;white-space:nowrap"
          >${m.active ? '✅ Активний' : '🚫 Вимкнено'}</button>
          <button
            onclick="editManager(${i})"
            style="padding:5px 10px;border-radius:8px;border:1px solid #e0e0e0;background:#fff;cursor:pointer;font-size:12px"
          >✏️ Змінити</button>
          <button
            onclick="removeManager(${i})"
            style="padding:5px 10px;border-radius:8px;border:1px solid #ffcdd2;background:#fff;color:#e53935;cursor:pointer;font-size:12px"
          >🗑 Видалити</button>
        </div>

      </div>
    </div>
  `).join('');
}

// ── Дії з менеджерами ───────────────────────────────

function toggleManager(i) {
  managers[i].active = !managers[i].active;
  renderList();
}

function removeManager(i) {
  managers.splice(i, 1);
  renderList();
}

function editManager(i) {
  const m = managers[i];
  document.getElementById('addName').value     = m.name;
  document.getElementById('addPhone').value    = m.phone;
  document.getElementById('addEmail').value    = m.email;
  document.getElementById('addTelegram').value = m.telegram;

  // Видалити старий запис — при натисканні "Додати" буде новий
  managers.splice(i, 1);
  renderList();

  document.getElementById('addName').scrollIntoView({ behavior: 'smooth' });
}

function clearAddForm() {
  document.getElementById('addName').value     = '';
  document.getElementById('addPhone').value    = '';
  document.getElementById('addEmail').value    = '';
  document.getElementById('addTelegram').value = '';
}

// ── Таби ────────────────────────────────────────────

function switchTab(tab) {
  const isManagers = tab === 'managers';
  document.getElementById('tabContentManagers').style.display  = isManagers ? '' : 'none';
  document.getElementById('tabContentTemplates').style.display = isManagers ? 'none' : '';
  document.getElementById('tabManagers').style.background  = isManagers ? '#FFC400' : '#f5f5f5';
  document.getElementById('tabTemplates').style.background = isManagers ? '#f5f5f5' : '#FFC400';
}

// ── Шаблони: завантажити ────────────────────────────

async function loadTemplates() {
  let settings = {};
  try {
    const res = await fetch(SETTINGS_GET_URL, { cache: 'no-store' });
    const data = await res.json();
    settings = data.settings || {};
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    const stored = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (stored) settings = JSON.parse(stored);
  }
  fillTemplateFields(settings);
}

function fillTemplateFields(settings) {
  const map = {
    tplNoCredit:       'ses_template_no_credit',
    tplNoCreditNoImg:  'ses_template_no_credit_no_img',
    tplWithCredit:     'ses_template_with_credit',
    tplWithCreditNoImg:'ses_template_with_credit_no_img',
    tplDriveFolder:    'ses_drive_folder',
  };
  Object.entries(map).forEach(([elId, key]) => {
    const el = document.getElementById(elId);
    if (el && settings[key]) el.value = settings[key];
  });
}

function readTemplateFields() {
  return {
    ses_template_no_credit:          document.getElementById('tplNoCredit').value.trim(),
    ses_template_no_credit_no_img:   document.getElementById('tplNoCreditNoImg').value.trim(),
    ses_template_with_credit:        document.getElementById('tplWithCredit').value.trim(),
    ses_template_with_credit_no_img: document.getElementById('tplWithCreditNoImg').value.trim(),
    ses_drive_folder:                document.getElementById('tplDriveFolder').value.trim(),
  };
}

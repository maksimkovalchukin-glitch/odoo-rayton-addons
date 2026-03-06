/* ======================================================
   AUTH — Перевірка доступу по Telegram username
   Дані зберігаються в n8n (Google Sheet) + localStorage fallback
====================================================== */

(function () {

  const MANAGERS_WEBHOOK = 'https://n8n.rayton.net/webhook/ses-managers';
  const STORAGE_KEY = 'rayton_managers';

  document.addEventListener('DOMContentLoaded', async () => {

    const tg = window.Telegram?.WebApp;

    // Завантажити список менеджерів
    let managers = [];
    try {
      const res = await fetch(MANAGERS_WEBHOOK, { cache: 'no-store' });
      const data = await res.json();
      managers = data.managers || [];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(managers));
    } catch {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) managers = JSON.parse(stored);
    }

    // Заповнити dropdown менеджерів динамічно
    populateManagerSelect(managers);

    // Не в Telegram (браузер/дев режим) — пропустити перевірку доступу
    if (!tg || !tg.initDataUnsafe) return;

    const username = tg.initDataUnsafe?.user?.username?.toLowerCase();
    if (!username) return;

    // Показати overlay під час перевірки
    const overlay = document.createElement('div');
    overlay.id = '__auth_overlay';
    overlay.style.cssText = [
      'position:fixed', 'inset:0', 'background:#fff', 'z-index:9999',
      'display:flex', 'align-items:center', 'justify-content:center',
      'font-family:sans-serif'
    ].join(';');
    overlay.innerHTML = '<div style="color:#888;font-size:14px">Перевірка доступу...</div>';
    document.body.appendChild(overlay);

    // Якщо список порожній — доступ відкритий (не налаштований)
    if (managers.length === 0) {
      overlay.remove();
      return;
    }

    const allowed = managers
      .filter(m => m.active)
      .map(m => m.telegram.replace(/^@/, '').toLowerCase());

    if (allowed.includes(username)) {
      const me = managers.find(
        m => m.telegram.replace(/^@/, '').toLowerCase() === username
      );
      if (me) {
        window.CURRENT_MANAGER = me;
        // Авто-вибір поточного менеджера в dropdown
        const sel = document.getElementById('manager');
        if (sel) {
          Array.from(sel.options).forEach(opt => {
            if (opt.value === me.name || opt.text === me.name) {
              sel.value = opt.value;
            }
          });
        }
        window.dispatchEvent(new CustomEvent('authReady', { detail: me }));
      }
      overlay.remove();
    } else {
      overlay.innerHTML = `
        <div style="text-align:center;padding:32px">
          <div style="font-size:52px;margin-bottom:16px">🚫</div>
          <div style="font-size:18px;font-weight:600;margin-bottom:10px">Доступ заборонено</div>
          <div style="color:#666;font-size:14px;line-height:1.5">
            @${username} не має доступу до застосунку.<br>
            Зверніться до адміністратора.
          </div>
        </div>
      `;
    }

  });

  function populateManagerSelect(managers) {
    const sel = document.getElementById('manager');
    if (!sel) return;

    const active = managers.filter(m => m.active);
    if (active.length === 0) return;

    const current = sel.value;

    // Залишити тільки перший option (placeholder)
    while (sel.options.length > 1) sel.remove(1);

    active.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.name;
      opt.textContent = m.name;
      sel.appendChild(opt);
    });

    if (current) sel.value = current;
  }

})();

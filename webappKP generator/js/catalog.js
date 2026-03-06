/* ======================================================
   CATALOG — Завантаження каталогу обладнання
   Зберігається в n8n Static Data, кешується в localStorage
====================================================== */

(function () {

  const CATALOG_URL     = 'https://n8n.rayton.net/webhook/ses-catalog';
  const CATALOG_STORAGE = 'rayton_catalog';

  window.CATALOG = null;

  async function loadCatalog() {
    try {
      const res  = await fetch(CATALOG_URL, { cache: 'no-store' });
      const data = await res.json();
      if (data.catalog) {
        window.CATALOG = data.catalog;
        localStorage.setItem(CATALOG_STORAGE, JSON.stringify(data.catalog));
        return;
      }
    } catch {
      // fallback to localStorage
    }

    const stored = localStorage.getItem(CATALOG_STORAGE);
    if (stored) {
      try { window.CATALOG = JSON.parse(stored); } catch { }
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    await loadCatalog();
    window.dispatchEvent(new CustomEvent('catalogReady', { detail: window.CATALOG }));
  });

  // Публічний API для settings.js
  window.CatalogAPI = {
    load: loadCatalog,

    async save(catalog) {
      localStorage.setItem(CATALOG_STORAGE, JSON.stringify(catalog));
      window.CATALOG = catalog;
      await fetch(CATALOG_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ catalog })
      });
    }
  };

})();

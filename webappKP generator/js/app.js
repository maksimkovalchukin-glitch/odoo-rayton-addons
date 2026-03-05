const tg = window.Telegram?.WebApp || null;

/* =========================
   Telegram init
========================= */

if (tg) {
  tg.expand();
  tg.ready();
}

/* =========================
   Navigation (Main Index Page)
========================= */

let selectedType = "uze";

function selectType(type) {
  selectedType = type;

  document
    .querySelectorAll(".type-card")
    .forEach(el => el.classList.remove("active"));

  const activeEl = document.getElementById(type);
  if (activeEl) activeEl.classList.add("active");
}

function goNext() {
  if (selectedType === "ses") {
    window.location.href = "ses2/index.html";
  } else {
    window.location.href = "uze/index.html";
  }
}

/* =========================
   Telegram Back Button
========================= */

function enableBack(url) {
  if (!tg) return;

  tg.BackButton.offClick();
  tg.BackButton.show();

  tg.BackButton.onClick(() => {
    window.location.href = url;
  });
}

/* ======================================================
   MAIN INIT
====================================================== */

document.addEventListener("DOMContentLoaded", () => {

  /* ---------- ROOT INDEX PAGE ---------- */
  if (document.querySelector(".type-card") &&
      typeof selectType === "function" &&
      typeof goNext === "function") {

    if (tg) {
      tg.BackButton.offClick();
      tg.BackButton.show();

      tg.BackButton.onClick(() => {
        tg.close(); // 🔥 Закриваємо WebApp на головній
      });
    }

    return;
  }

 /* ---------- UZE PAGE ---------- */
if (document.getElementById("uze_model")) {

  // 🔥 ДОДАЄМО НАЗАД ДЛЯ UZE
  enableBack("../index.html");

  initUZE();
  return;
}


  // SES сторінки мають власні js файли
});

/* ======================================================
   UZE LOGIC
====================================================== */

function initUZE() {

  const WEBHOOK_URL =
    "https://n8n.rayton.net/webhook/34d36afc-8cda-4ddd-9e8d-2f057e9dc620";

  const submitBtn = document.getElementById("submitBtn");
  const modelSelect = document.getElementById("uze_model");
  const qtySelect = document.getElementById("uze_qty");
  const qtyError = document.getElementById("qtyError");

  const requiredFields = [
    "project_name",
    "manager",
    "region",
    "uze_model",
    "uze_qty",
    "uze_vat",
    "equipment_vat",
    "currency",
    "usage_type",
    "delivery_term",
    "payment_terms",
    "delivery_terms"
  ];

  const modelLimits = {
    "RESS-100-215 Режим off-grid (авт. шовний) з контролером": 5,
    "RESS-125-241 (з контролером)": 5,
    "RESS-125-241 (без контролера)": 5,
    "RESS-100-233L": 1,
    "RESS-80-241": 1,
    "RESS-2500-5015": 50,
    "RESS-1000-4180": 50,
    "RESS-1125-2170 Режим off-grid (шовний)": 1,
    "RESS-1125-2170 Режим off-grid (безшовний)": 1,
    "RESS-100-215 Режим off-grid (ручний) без контролера": 5,
    "RESS-1250-4180": 50,
    "RESS-1500-4180": 50,
    "RESS-1250-5015": 50,
    "RESS-1500-5015": 50,
    "RESS-1000-5015": 50,
    "RESS-1725-3344": 50,
    "RESS-125-257": 0,
    "RESS-1000-3344": 0,
    "RESS-1250-3344": 0,
    "RESS-1500-3344": 0,
    "RESS-1725-4180": 0,
    "RESS-2000-4180": 0,
    "RESS-1725-5015": 0,
    "RESS-500-1000 лише off-grid": 0,
    "RESS-100-241": 0,
    "RESS-50-241": 0,
    "RESS-60-241": 0,
    "RESS-125-261 Режим off-grid (не швидкий) без STS": 0,
    "RESS-125-261 Режим off-grid (швидкий) з STS": 0
  };

  function validateQty() {
    const selectedModel = modelSelect.value;
    const selectedQty = parseInt(qtySelect.value);
    const maxAllowed = modelLimits[selectedModel];

    if (!maxAllowed) return true;

    if (selectedQty > maxAllowed) {
      qtySelect.classList.add("error");
      qtyError.style.display = "block";
      qtyError.innerText = `Максимально дозволено: ${maxAllowed}`;
      return false;
    }

    qtySelect.classList.remove("error");
    qtyError.style.display = "none";
    return true;
  }

  function validateForm() {
    let isValid = true;

    requiredFields.forEach(id => {
      const field = document.getElementById(id);
      if (!field || !field.value) isValid = false;
    });

    if (!validateQty()) isValid = false;

    submitBtn.disabled = !isValid;
  }

  document.querySelectorAll("input, select").forEach(el => {
    el.addEventListener("input", validateForm);
    el.addEventListener("change", validateForm);
  });

  validateForm();

  submitBtn.addEventListener("click", async () => {

    submitBtn.disabled = true;
    submitBtn.innerText = "Формування КП...";

    const chatId =
      tg?.initDataUnsafe?.chat?.id ||
      tg?.initDataUnsafe?.user?.id ||
      null;

    const data = {};

    requiredFields.forEach(id => {
      data[id] = document.getElementById(id)?.value || "";
    });

    data.chat_id = chatId;

    await sendToWebhook(WEBHOOK_URL, data, submitBtn);
  });
}

/* ======================================================
   Shared Webhook Sender
====================================================== */

async function sendToWebhook(url, data, button) {
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });

    if (tg) {
      tg.showAlert("КП формується та буде надіслано в цей чат");
      setTimeout(() => tg.close(), 800);
    } else {
      alert("КП формується");
    }

  } catch (err) {
    button.innerText = "Помилка. Спробуйте ще раз";
    button.disabled = false;
  }
}

/* ======================================================
   SES — MANUAL MODE (FINAL PRODUCTION - STABLE)
====================================================== */

document.addEventListener("DOMContentLoaded", () => {

  /* ======================================================
     BACK BUTTON
  ====================================================== */
  if (typeof enableBack === "function") {
    enableBack("../index.html");
  }

  const WEBHOOK_URL =
    "https://n8n.rayton.net/webhook/bb30efd0-c82c-4b1e-9f5c-4a34c6a3dbe6";

  const tg = window.Telegram?.WebApp || null;

  /* ======================================================
     DOM
  ====================================================== */

  const submitBtn = document.getElementById("submitBtn");
  const recommendationBox = document.getElementById("recommendationBox");

  const panelSelect = document.getElementById("module_type");
  const panelInput = document.getElementById("panel_qty");

  const realDCInput = document.getElementById("real_dc");
  const realACInput = document.getElementById("real_ac");
  const recommendedACInput = document.getElementById("recommended_ac");

  const currencySelect = document.getElementById("currency");
  const priceInput = document.getElementById("price_per_kw");

  const CONFIG = {
    dcAcRatioTarget: 1.28,
    minAC: 30,
    minRatio: 1.1,
    maxRatio: 1.5
  };

  const inverterFields = [
    { model: "inverter_1_model", qty: "inverter_1_qty" },
    { model: "inverter_2_model", qty: "inverter_2_qty" },
    { model: "inverter_3_model", qty: "inverter_3_qty" }
  ];

  /* ======================================================
     💱 CURRENCY UI INDICATOR
  ====================================================== */

  function updateCurrencyHint() {
    const currency = currencySelect.value;

    if (currency === "EUR") {
      priceInput.placeholder = "Введіть ціну за кВт (€)";
      priceInput.setAttribute("data-currency", "€");
    } else {
      priceInput.placeholder = "Введіть ціну за кВт ($)";
      priceInput.setAttribute("data-currency", "$");
    }
  }

  currencySelect.addEventListener("change", updateCurrencyHint);
  updateCurrencyHint();

  /* ======================================================
     CALCULATIONS
  ====================================================== */

  function calculateDC() {
    const panelPowerW = Number(panelSelect.selectedOptions[0]?.dataset?.watt);
    const panelQty = Number(panelInput.value);
    if (!panelPowerW || !panelQty) return 0;
    return (panelPowerW * panelQty) / 1000;
  }

  function calculateAC() {
    let total = 0;

    inverterFields.forEach(field => {
      const modelPower = Number(document.getElementById(field.model)?.value);
      const qty = Number(document.getElementById(field.qty)?.value) || 0;

      if (modelPower && qty > 0) {
        total += modelPower * qty;
      }
    });

    return total;
  }

  function updateRecommendation(realDC, realAC) {

    if (!realDC) {
      recommendationBox.innerText = "Оберіть панелі та кількість";
      recommendationBox.style.color = "";
      recommendedACInput.value = "";
      return;
    }

    const recommendedAC = realDC / CONFIG.dcAcRatioTarget;
    recommendedACInput.value = recommendedAC.toFixed(2);

    if (!realAC) {
      recommendationBox.innerHTML =
        `🔹 DC: <b>${realDC.toFixed(2)} кВт</b><br>
         🔹 Рекомендований AC ≈ <b>${recommendedAC.toFixed(1)} кВт</b>`;
      recommendationBox.style.color = "#555";
      return;
    }

    const ratio = realDC / realAC;

    if (ratio < CONFIG.minRatio || ratio > CONFIG.maxRatio) {
      recommendationBox.innerHTML =
        `⚠️ DC/AC = ${ratio.toFixed(2)} (поза нормою ${CONFIG.minRatio}–${CONFIG.maxRatio})`;
      recommendationBox.style.color = "orange";
    } else {
      recommendationBox.innerHTML =
        `✅ DC/AC = ${ratio.toFixed(2)} (норма)`;
      recommendationBox.style.color = "green";
    }
  }

  /* ======================================================
     VALIDATION
  ====================================================== */

  function validateForm() {

    let valid = true;

    const requiredFields = [
      "project_name",
      "manager",
      "region",
      "mount_type",
      "currency",
      "price_vat_type",
      "material_type",
      "ses_type",
      "power_regulation",
      "monitoring_device"
    ];

    requiredFields.forEach(id => {
      const field = document.getElementById(id);
      if (!field || !field.value) valid = false;
    });

    if (!panelSelect.value) valid = false;

    const realDC = calculateDC();
    const realAC = calculateAC();

    realDCInput.value = realDC ? realDC.toFixed(2) : "";
    realACInput.value = realAC ? realAC.toFixed(2) : "";

    updateRecommendation(realDC, realAC);

    if (realDC <= 0) valid = false;
    if (realAC < CONFIG.minAC) valid = false;

    submitBtn.disabled = !valid;
  }

  document.querySelectorAll("input, select").forEach(el => {
    el.addEventListener("input", validateForm);
    el.addEventListener("change", validateForm);
  });

  validateForm();

  /* ======================================================
     SUBMIT
  ====================================================== */

  submitBtn.addEventListener("click", async () => {

    submitBtn.disabled = true;
    submitBtn.innerText = "Формування КП...";

    const chatId =
      tg?.initDataUnsafe?.chat?.id ||
      tg?.initDataUnsafe?.user?.id ||
      null;

    const formData = {
      project_name: document.getElementById("project_name").value,
      manager: document.getElementById("manager").value,
      region: document.getElementById("region").value,

      currency: currencySelect.value,
      price_vat_type: document.getElementById("price_vat_type").value,
      price_per_kw: priceInput?.value || "",

      module_type: panelSelect.value,
      panel_qty: panelInput.value,

      manager_phone: window.CURRENT_MANAGER?.phone || "",
      manager_email: window.CURRENT_MANAGER?.email || "",

      real_dc: realDCInput.value,
      real_ac: realACInput.value,

      inverter_1_model: document.getElementById("inverter_1_model")?.selectedOptions[0]?.text || "",
      inverter_1_qty: document.getElementById("inverter_1_qty")?.value || 0,
      inverter_2_model: document.getElementById("inverter_2_model")?.selectedOptions[0]?.text || "",
      inverter_2_qty: document.getElementById("inverter_2_qty")?.value || 0,
      inverter_3_model: document.getElementById("inverter_3_model")?.selectedOptions[0]?.text || "",
      inverter_3_qty: document.getElementById("inverter_3_qty")?.value || 0,

      mount_type: document.getElementById("mount_type").value,
      material_type: document.getElementById("material_type").value,
      ses_type: document.getElementById("ses_type").value,
      power_regulation: document.getElementById("power_regulation").value,
      monitoring_device: document.getElementById("monitoring_device").value,

      calculation_mode: "manual",

      chat_id: chatId
    };

    const calcResult = window.CalculateEngine?.calculate(formData, window.CATALOG);
    if (!calcResult?.ok) {
      submitBtn.innerText = calcResult?.error || "Помилка розрахунку";
      submitBtn.disabled = false;
      return;
    }

    const payload = {
      ...formData,
      template_vars:  calcResult.template_vars,
      line_items:     calcResult.line_items,
      file_name:      calcResult.file_name,
      doc_copy_name:  calcResult.doc_copy_name,
      final_total:    calcResult.final_total,
      dc_kw:          calcResult.dc_kw,
    };

    try {

      await fetch(WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (tg) {
        tg.showAlert("КП формується та буде надіслано в цей чат");
        setTimeout(() => tg.close(), 800);
      }

    } catch (err) {
      submitBtn.innerText = "Помилка. Спробуйте ще раз";
      submitBtn.disabled = false;
    }

  });



  // Авто-вибір менеджера в dropdown коли auth перевірив доступ
  window.addEventListener('authReady', (e) => {
    const managerSelect = document.getElementById('manager');
    if (\!managerSelect || \!e.detail?.name) return;
    Array.from(managerSelect.options).forEach(opt => {
      if (opt.value === e.detail.name || opt.text === e.detail.name) {
        managerSelect.value = opt.value;
        validateForm();
      }
    });
  });

});

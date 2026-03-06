/* ======================================================
   SES — ROOF MODE (UNIFIED WEBHOOK STRUCTURE)
====================================================== */

document.addEventListener("DOMContentLoaded", () => {

  if (typeof enableBack === "function") {
    enableBack("../index.html");
  }

  const WEBHOOK_URL =
    "https://n8n.rayton.net/webhook/bb30efd0-c82c-4b1e-9f5c-4a34c6a3dbe6";

  const tg = window.Telegram?.WebApp || null;

  const submitBtn = document.getElementById("submitBtn");
  const areaInput = document.getElementById("roof_area");
  const roofTypeSelect = document.getElementById("roof_mount_type");

  const currencySelect = document.getElementById("currency");
  const priceInput = document.getElementById("price_per_kw");

  const CONFIG = {
    dcAcRatio: 1.28,
    minRatio: 1.1,
    maxRatio: 1.5,
    minAC: 100,
    minDC: 100,
    wPerM2Tilted: 130.55,
    wPerM2Flat: 229.33
  };

  const INVERTERS = [
    { name: "Huawei SUN2000-150KTL-G0", power: 150 },
    { name: "Huawei SUN2000-115KTL-M2", power: 115 },
    { name: "Huawei SUN2000-100KTL-M2", power: 100 },
    { name: "Huawei SUN2000-50KTL-M3", power: 50 },
    { name: "Huawei SUN2000-30KTL-M3", power: 30 }
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
     HELPERS
  ====================================================== */

  function getSelectedModulePowerKW() {
    const moduleSelect = document.getElementById("module_type");
    const powerW = Number(moduleSelect.selectedOptions[0]?.dataset?.watt);
    if (!powerW) return 0;
    return powerW / 1000;
  }

  function calculatePlannedDC(area, roofType) {
    const coef =
      roofType === "Під нахилом"
        ? CONFIG.wPerM2Tilted
        : CONFIG.wPerM2Flat;

    return (area * coef) / 1000;
  }

  /* ======================================================
     🔥 ПІДБІР ІНВЕРТОРІВ
  ====================================================== */

  function selectBestInverters(targetAC) {

    const sorted = [...INVERTERS].sort((a, b) => b.power - a.power);

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

    if (remaining > 0) {
      for (let inv of sorted) {
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

    const totalAC = result.reduce((sum, i) => sum + i.power * i.qty, 0);

    while (result.length < 3) {
      result.push({ name: "", power: 0, qty: 0 });
    }

    return {
      list: result.slice(0, 3),
      totalAC
    };
  }

  /* ======================================================
     VALIDATION
  ====================================================== */

  function validateForm() {

    let isValid = true;

    const required = [
      "project_name",
      "manager",
      "region",
      "module_type",
      "mount_type",
      "material_type",
      "ses_type",
      "power_regulation",
      "monitoring_device",
      "currency",
      "price_vat_type",
      "price_per_kw",
      "roof_area",
      "roof_mount_type"
    ];

    required.forEach(id => {
      const field = document.getElementById(id);
      if (!field || !field.value) isValid = false;
    });

    const area = Number(areaInput.value);
    const roofType = roofTypeSelect.value;

    if (!area || area <= 0 || !roofType) {
      isValid = false;
    } else {
      const plannedDC = calculatePlannedDC(area, roofType);
      if (plannedDC < CONFIG.minDC) isValid = false;
    }

    submitBtn.disabled = !isValid;
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

    const area = Number(areaInput.value);
    const roofType = roofTypeSelect.value;

    const plannedDC = calculatePlannedDC(area, roofType);

    let targetAC = plannedDC / CONFIG.dcAcRatio;
    if (targetAC < CONFIG.minAC) targetAC = CONFIG.minAC;

    const inverterResult = selectBestInverters(targetAC);

    if (!inverterResult) {
      submitBtn.innerText = "Помилка підбору інверторів";
      submitBtn.disabled = false;
      return;
    }

    const realAC = inverterResult.totalAC;
    const realDC = realAC * CONFIG.dcAcRatio;

    if (realAC < CONFIG.minAC) {
      submitBtn.innerText = "AC менше 100 кВт";
      submitBtn.disabled = false;
      return;
    }

    const ratio = realDC / realAC;
    if (ratio < CONFIG.minRatio || ratio > CONFIG.maxRatio) {
      submitBtn.innerText = "DC/AC поза нормою";
      submitBtn.disabled = false;
      return;
    }

    const modulePowerKW = getSelectedModulePowerKW();
    if (!modulePowerKW) {
      submitBtn.innerText = "Оберіть тип панелі";
      submitBtn.disabled = false;
      return;
    }

    const panelQty = Math.ceil(realDC / modulePowerKW);

    const chatId =
      tg?.initDataUnsafe?.chat?.id ||
      tg?.initDataUnsafe?.user?.id ||
      null;

    const formData = {
      project_name: document.getElementById("project_name").value,
      manager: document.getElementById("manager").value,
      region: document.getElementById("region").value,

      module_type: document.getElementById("module_type").value,
      panel_qty: panelQty,

      manager_phone: window.CURRENT_MANAGER?.phone || "",
      manager_email: window.CURRENT_MANAGER?.email || "",

      real_dc: realDC.toFixed(2),
      real_ac: realAC.toFixed(2),

      inverter_1_model: inverterResult.list[0].name,
      inverter_1_qty: inverterResult.list[0].qty,
      inverter_2_model: inverterResult.list[1].name,
      inverter_2_qty: inverterResult.list[1].qty,
      inverter_3_model: inverterResult.list[2].name,
      inverter_3_qty: inverterResult.list[2].qty,

      mount_type: document.getElementById("mount_type").value,
      material_type: document.getElementById("material_type").value,
      ses_type: document.getElementById("ses_type").value,
      power_regulation: document.getElementById("power_regulation").value,
      monitoring_device: document.getElementById("monitoring_device").value,

      currency: currencySelect.value,
      price_vat_type: document.getElementById("price_vat_type").value,
      price_per_kw: priceInput.value,

      roof_area: area,
      roof_type: roofType,

      calculation_mode: "roof",
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

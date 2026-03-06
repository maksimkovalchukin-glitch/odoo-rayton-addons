/* ======================================================
   SES — POWER MODE (SMART INVERTER SELECTION)
====================================================== */

document.addEventListener("DOMContentLoaded", () => {

  if (typeof enableBack === "function") {
    enableBack("../index.html");
  }

  const WEBHOOK_URL =
    "https://n8n.rayton.net/webhook/bb30efd0-c82c-4b1e-9f5c-4a34c6a3dbe6";

  const tg = window.Telegram?.WebApp || null;

  const submitBtn = document.getElementById("submitBtn");
  const dcInput = document.getElementById("planned_power");

  const currencySelect = document.getElementById("currency");
  const priceInput = document.getElementById("price_per_kw");

  const CONFIG = {
    dcAcRatio: 1.28,
    minRatio: 1.1,
    maxRatio: 1.5,
    minAC: 100
  };

  const INVERTERS = [
    { name: "Huawei SUN2000-150KTL-G0", power: 150 },
    { name: "Huawei SUN2000-115KTL-M2", power: 115 },
    { name: "Huawei SUN2000-100KTL-M2", power: 100 },
    { name: "Huawei SUN2000-50KTL-M3", power: 50 },
    { name: "Huawei SUN2000-30KTL-M3", power: 30 }
  ];

  /* ======================================================
     SMART INVERTER SELECTION
  ====================================================== */

  function selectBestInverters(targetAC) {

    let bestOption = null;
    let smallestOversize = Infinity;

    const maxQty = 5; // максимум інверторів одного типу

    for (let i = 0; i < INVERTERS.length; i++) {
      for (let j = 0; j < INVERTERS.length; j++) {
        for (let k = 0; k < INVERTERS.length; k++) {

          for (let qi = 0; qi <= maxQty; qi++) {
            for (let qj = 0; qj <= maxQty; qj++) {
              for (let qk = 0; qk <= maxQty; qk++) {

                if (qi + qj + qk === 0) continue;

                const totalAC =
                  qi * INVERTERS[i].power +
                  qj * INVERTERS[j].power +
                  qk * INVERTERS[k].power;

                if (totalAC < CONFIG.minAC) continue;
                if (totalAC < targetAC) continue;

                const realDC = totalAC * CONFIG.dcAcRatio;
                const ratio = realDC / totalAC;

                if (ratio < CONFIG.minRatio || ratio > CONFIG.maxRatio)
                  continue;

                const oversize = totalAC - targetAC;

                if (oversize < smallestOversize) {
                  smallestOversize = oversize;

                  bestOption = {
                    list: [
                      { ...INVERTERS[i], qty: qi },
                      { ...INVERTERS[j], qty: qj },
                      { ...INVERTERS[k], qty: qk }
                    ].filter(x => x.qty > 0),
                    totalAC
                  };
                }
              }
            }
          }
        }
      }
    }

    if (!bestOption) return null;

    while (bestOption.list.length < 3) {
      bestOption.list.push({ name: "", power: 0, qty: 0 });
    }

    return bestOption;
  }

  /* ======================================================
     HELPERS
  ====================================================== */

  function getSelectedModulePowerKW() {
    const moduleSelect = document.getElementById("module_type");
    const powerW = Number(moduleSelect.selectedOptions[0]?.dataset?.watt);
    if (!powerW) return 0;
    return powerW / 1000;
  }

  /* ======================================================
     SUBMIT
  ====================================================== */

  submitBtn.addEventListener("click", async () => {

    submitBtn.disabled = true;
    submitBtn.innerText = "Формування КП...";

    const plannedDC = Number(dcInput.value);

    let targetAC = plannedDC / CONFIG.dcAcRatio;
    if (targetAC < CONFIG.minAC) targetAC = CONFIG.minAC;

    const inverterResult = selectBestInverters(targetAC);

    if (!inverterResult) {
      submitBtn.innerText = "Не знайдено оптимальну конфігурацію";
      submitBtn.disabled = false;
      return;
    }

    const realAC = inverterResult.totalAC;
    const realDC = realAC * CONFIG.dcAcRatio;

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

    const moduleSelect = document.getElementById("module_type");

    const formData = {
      project_name: document.getElementById("project_name").value,
      manager: document.getElementById("manager").value,
      region: document.getElementById("region").value,

      module_type: moduleSelect.value,
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

      currency: document.getElementById("currency").value,
      price_vat_type: document.getElementById("price_vat_type").value,
      price_per_kw: document.getElementById("price_per_kw").value,

      planned_dc: plannedDC,
      calculation_mode: "power",

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

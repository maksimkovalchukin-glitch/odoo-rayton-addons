/* ================================================================
   n8n Code Node — Генерація графіків КП СЕС

   Запускається ПІСЛЯ вузла "Code: Calculate"

   ВХІД:
     $('Code: Calculate').first().json  — результат розрахунку

   ВИХІД:
     year_chart_url  — URL QuickChart.io для річного графіка
     day_chart_url   — URL QuickChart.io для денного графіка
     yearly_gen_kwh  — річна генерація (кВт·год)
     yearly_gen_mwh  — річна генерація (МВт·год, округлено)

   QuickChart.io: https://quickchart.io/chart?c=<JSON>
   Безкоштовний, повертає PNG 800×400.
================================================================ */

// ────────────────────────────────────────────────────────────────
// 1. МІСЯЧНІ КОЕФІЦІЄНТИ ГЕНЕРАЦІЇ (кВт·год на 1 кВт DC за місяць)
//    Джерело: PVGis / SODA MERRA-2 дані для України
//    Порядок: Січ, Лют, Бер, Квіт, Трав, Черв, Лип, Серп, Вер, Жовт, Лис, Груд
// ────────────────────────────────────────────────────────────────

const MONTHLY_COEF = {
  // Північ
  'Чернігівська область':     [22, 33, 65, 98, 118, 120, 122, 113, 85, 50, 24, 17],
  'Сумська область':          [23, 34, 66, 99, 119, 121, 123, 114, 86, 51, 25, 18],
  'Житомирська область':      [24, 35, 67, 100, 120, 122, 124, 115, 87, 52, 25, 18],

  // Захід
  'Волинська область':        [24, 36, 67, 100, 119, 120, 122, 112, 85, 51, 25, 17],
  'Рівненська область':       [24, 36, 68, 101, 120, 121, 123, 113, 86, 52, 25, 18],
  'Львівська область':        [26, 38, 72, 106, 123, 124, 127, 118, 90, 56, 27, 19],
  'Закарпатська область':     [30, 44, 80, 113, 130, 131, 135, 126, 98, 62, 31, 22],
  'Івано-Франківська область':[27, 40, 74, 107, 124, 125, 128, 119, 91, 57, 28, 20],
  'Тернопільська область':    [26, 38, 71, 105, 122, 123, 126, 117, 89, 55, 26, 18],
  'Хмельницька область':      [26, 38, 71, 105, 122, 123, 126, 117, 89, 55, 26, 18],
  'Вінницька область':        [27, 40, 74, 108, 126, 127, 130, 120, 92, 57, 27, 19],
  'Чернівецька область':      [28, 42, 78, 112, 129, 130, 134, 125, 96, 60, 29, 21],

  // Центр
  'м. Київ':                  [25, 37, 71, 105, 124, 126, 128, 118, 89, 53, 25, 18],
  'Київська область':         [25, 37, 70, 104, 123, 125, 127, 117, 88, 52, 25, 17],
  'Черкаська область':        [28, 42, 78, 112, 131, 133, 135, 125, 95, 58, 27, 19],
  'Полтавська область':       [29, 43, 79, 114, 133, 135, 137, 127, 97, 60, 28, 20],
  'Кіровоградська область':   [31, 47, 85, 119, 138, 140, 143, 133, 103, 64, 30, 22],

  // Схід
  'Харківська область':       [28, 43, 80, 114, 133, 135, 138, 128, 97, 59, 27, 19],
  'Дніпропетровська область': [32, 49, 87, 122, 141, 143, 146, 136, 105, 66, 31, 22],
  'Донецька область':         [30, 46, 84, 118, 137, 139, 142, 132, 101, 63, 30, 21],
  'Запорізька область':       [35, 53, 95, 131, 150, 152, 156, 145, 113, 72, 34, 25],
  'Луганська область':        [29, 44, 81, 115, 134, 136, 139, 129, 98, 60, 28, 20],

  // Південь
  'Одеська область':          [38, 57, 100, 137, 156, 158, 163, 151, 118, 76, 37, 27],
  'Миколаївська область':     [36, 55, 98, 134, 153, 155, 160, 148, 115, 73, 35, 26],
  'Херсонська область':       [37, 56, 100, 136, 155, 157, 162, 150, 117, 75, 36, 26],

  // Default (середня Україна якщо регіон не знайдено)
  'default':                  [28, 42, 77, 111, 130, 132, 134, 124, 95, 59, 28, 19],
};

const MONTHS_UK = ['Січ', 'Лют', 'Бер', 'Квіт', 'Трав', 'Черв', 'Лип', 'Серп', 'Вер', 'Жовт', 'Лис', 'Груд'];

// Денні коефіцієнти (частки від добового максимуму) — типовий літній день
// Кожна точка = година (0..23), відносна частка генерації 0..1
const DAILY_HOURLY_PROFILE = [
  0, 0, 0, 0, 0, 0.03,    // 0-5 год
  0.08, 0.18, 0.38, 0.58, 0.75, 0.88,  // 6-11 год
  0.97, 1.00, 0.97, 0.88, 0.75, 0.58,  // 12-17 год
  0.35, 0.15, 0.05, 0.01, 0, 0,         // 18-23 год
];

// ────────────────────────────────────────────────────────────────
// 2. ВХІДНІ ДАНІ
// ────────────────────────────────────────────────────────────────

const calc = $('Code: Calculate').first().json;

const dcKW      = parseFloat(calc.dc_kw)  || 0;
const region    = calc.region || 'default';
const tariffNow = parseFloat(calc.tariff_now) || 0;
const creditEnabled = calc.credit_enabled || false;
const creditMonths  = parseInt(calc.credit_months) || 60;
const monthlyPaymentUAH = parseFloat(calc.monthly_payment_uah) || 0;
const monthlySavingsUAH = parseFloat(calc.monthly_savings_uah) || 0;

const coefs = MONTHLY_COEF[region] || MONTHLY_COEF['default'];

// ────────────────────────────────────────────────────────────────
// 3. МІСЯЧНА ГЕНЕРАЦІЯ (кВт·год)
// ────────────────────────────────────────────────────────────────

const monthlyKWh = coefs.map(c => Math.round(c * dcKW));
const yearlyKWh  = monthlyKWh.reduce((s, v) => s + v, 0);
const yearlyMWh  = Math.round(yearlyKWh / 100) / 10; // 1 знак після коми

// Пік — найкращий місяць
const peakIdx  = monthlyKWh.indexOf(Math.max(...monthlyKWh));
const peakKWh  = monthlyKWh[peakIdx];

// ────────────────────────────────────────────────────────────────
// 4. ДЕННА ГЕНЕРАЦІЯ (для пікового місяця)
//    Беремо денну генерацію пікового місяця та розподіляємо по годинах
// ────────────────────────────────────────────────────────────────

// Середньодобова генерація для пікового місяця (кВт·год/день)
const daysInPeakMonth = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][peakIdx];
const dailyAvgKWh     = peakKWh / daysInPeakMonth;

// Профіль дня (кВт·год за годину)
const dailyHourlyKWh  = DAILY_HOURLY_PROFILE.map(factor => +(factor * dailyAvgKWh).toFixed(1));

// Години для підписів (тільки денні)
const hourLabels = Array.from({ length: 24 }, (_, i) => `${i}:00`);

// ────────────────────────────────────────────────────────────────
// 5. QUICKCHART.IO — РІЧНИЙ ГРАФІК
// ────────────────────────────────────────────────────────────────

const yearChartConfig = {
  type: 'bar',
  data: {
    labels: MONTHS_UK,
    datasets: [{
      label: 'Генерація, кВт·год',
      data: monthlyKWh,
      backgroundColor: monthlyKWh.map((_, i) =>
        i === peakIdx ? '#FFC400' : '#4A90D9'
      ),
      borderRadius: 6,
    }],
  },
  options: {
    plugins: {
      legend:  { display: false },
      title:   {
        display: true,
        text:    `Річна генерація СЕС ${dcKW.toFixed(0)} кВт · ${region}`,
        font:    { size: 14 },
      },
      datalabels: {
        anchor: 'end',
        align:  'top',
        font:   { size: 10 },
        formatter: (v) => v >= 1000 ? `${(v/1000).toFixed(1)}МВт` : `${v}`,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        title: { display: true, text: 'кВт·год' },
        grid: { color: '#f0f0f0' },
      },
      x: { grid: { display: false } },
    },
  },
};

// ────────────────────────────────────────────────────────────────
// 6. QUICKCHART.IO — ДЕННИЙ ГРАФІК
// ────────────────────────────────────────────────────────────────

const dayChartConfig = {
  type: 'line',
  data: {
    labels: hourLabels,
    datasets: [{
      label: `Генерація (${MONTHS_UK[peakIdx]}, кВт·год/год)`,
      data: dailyHourlyKWh,
      borderColor: '#FFC400',
      backgroundColor: 'rgba(255,196,0,0.15)',
      borderWidth: 2.5,
      pointRadius: 3,
      fill: true,
      tension: 0.4,
    }],
  },
  options: {
    plugins: {
      legend: { display: false },
      title: {
        display: true,
        text:    `Денна генерація (${MONTHS_UK[peakIdx]}, середній день) · СЕС ${dcKW.toFixed(0)} кВт`,
        font:    { size: 14 },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        title: { display: true, text: 'кВт·год/год' },
        grid:  { color: '#f0f0f0' },
      },
      x: {
        grid: { display: false },
        ticks: { maxTicksLimit: 12 },
      },
    },
  },
};

// ────────────────────────────────────────────────────────────────
// 7. ФОРМУВАННЯ URL QUICKCHART
// ────────────────────────────────────────────────────────────────

function toChartUrl(config, width = 800, height = 380) {
  const json = encodeURIComponent(JSON.stringify(config));
  return `https://quickchart.io/chart?w=${width}&h=${height}&bkg=white&c=${json}`;
}

const yearChartUrl = toChartUrl(yearChartConfig);
const dayChartUrl  = toChartUrl(dayChartConfig);

// ────────────────────────────────────────────────────────────────
// 8. ЕКОНОМІКА (беремо з ses_calculate, доповнюємо точною генерацією)
// ────────────────────────────────────────────────────────────────

// Точна річна економія на основі регіональних даних
const selfConsumptionRatio = 0.80;
const yearlyEconomyUAH     = tariffNow > 0
  ? Math.round(yearlyKWh * selfConsumptionRatio * tariffNow)
  : Math.round(calc.monthly_savings_uah * 12) || 0;

// ────────────────────────────────────────────────────────────────
// 9. ВИХІД
// ────────────────────────────────────────────────────────────────

return [{
  json: {
    // Передаємо все з попереднього вузла
    ...calc,

    // Графіки
    year_chart_url: yearChartUrl,
    day_chart_url:  dayChartUrl,

    // Генерація
    monthly_kwh:    monthlyKWh,
    yearly_kwh:     yearlyKWh,
    yearly_mwh:     yearlyMWh,
    peak_month:     MONTHS_UK[peakIdx],

    // Економіка (уточнена з регіональними даними)
    yearly_kwh:     yearlyKWh,
    yearly_mwh:     yearlyMWh,
    yearly_economy: yearlyEconomyUAH,
    peak_month:     MONTHS_UK[peakIdx],

    // Перерахунок окупності з регіональними даними
    // (точніше ніж fallback 1100 год/рік у ses_calculate)
    ...(() => {
      const totalUAH = (parseFloat(calc.total_usd) || 0) * (parseFloat(calc.rate_usd) || 41.2);
      let paybackStr = '—';
      if (yearlyEconomyUAH > 0 && totalUAH > 0) {
        const py    = totalUAH / yearlyEconomyUAH;
        const pyInt = Math.floor(py);
        const pyMon = Math.round((py - pyInt) * 12);
        paybackStr  = pyMon > 0 ? `${pyInt} р. ${pyMon} міс.` : `${pyInt} р.`;
      }
      return {
        payback_str_regional: paybackStr,
        template_vars: {
          ...calc.template_vars,
          '{{yearly_gen}}':   `${yearlyMWh} МВт·год`,
          '{{payback}}':      paybackStr,
          '{{tariff_now}}':   tariffNow ? `${tariffNow.toFixed(2)} грн/кВт·год` : calc.template_vars?.['{{tariff_now}}'] || '',
          '{{total_profit}}': `${Math.round(yearlyEconomyUAH / 1000)} тис. грн/рік`,
        },
      };
    })(),
  }
}];

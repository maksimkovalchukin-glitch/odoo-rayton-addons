/* Генератор workflow_ses.json для n8n */
const fs   = require('fs');
const path = require('path');
const dir  = path.join(__dirname);

const calculateCode = fs.readFileSync(path.join(dir, 'ses_calculate.js'), 'utf8');
const chartsCode    = fs.readFileSync(path.join(dir, 'ses_charts.js'),    'utf8');
const uploadCode    = fs.readFileSync(path.join(dir, 'upload_custom_image.js'), 'utf8');

const afterBranchCode = `
// Об'єднання гілок: з custom image або без
const calc = $('Code: Charts').first().json;

let customImageDriveId  = null;
let customImageDriveUrl = null;

try {
  const imageItems = $('Drive: Upload Custom Image').all();
  if (imageItems.length > 0) {
    customImageDriveId  = imageItems[0].json.id;
    customImageDriveUrl = \`https://drive.google.com/uc?export=view&id=\${customImageDriveId}\`;
  }
} catch (e) {
  // Вузол не виконувався (гілка без зображення) — залишаємо null
}

return [{
  json: {
    ...calc,
    custom_image_drive_id:  customImageDriveId,
    custom_image_drive_url: customImageDriveUrl,
  }
}];
`.trim();

const findEmptyRowsCode = `
// Після replaceAllText порожні рядки таблиці містять лише пусті рядки.
// Видаляємо їх знизу вверх, щоб уникнути зміщення індексів.
const docData = $json;
const calc    = $('Code: Підготовка Docs').first().json;
const docId   = calc.docId;

const content = docData.tabs?.[0]?.documentTab?.body?.content || docData.body?.content || [];

const requests = [];

for (const el of content) {
  if (!el.table) continue;

  // Обробляємо лише таблицю специфікації — ту що містить "ОБЛАДНАННЯ ТА МАТЕРІАЛИ"
  // (в документі є декілька таблиць з пустими рядками — структурні, видаляти не треба)
  const isCostTable = el.table.tableRows.some(row => {
    const firstCell = (row.tableCells[0]?.content || [])
      .flatMap(p => (p.paragraph?.elements || []))
      .map(e => e.textRun?.content || '')
      .join('')
      .trim();
    return firstCell.includes('ОБЛАДНАННЯ');
  });
  if (!isCostTable) continue;

  const tableStartIndex = el.startIndex;
  const emptyRowIndices = [];

  el.table.tableRows.forEach((row, rowIndex) => {
    const allEmpty = row.tableCells.every(cell => {
      const cellText = (cell.content || [])
        .flatMap(p => (p.paragraph?.elements || []))
        .map(e => e.textRun?.content || '')
        .join('')
        .trim();
      return cellText === '';
    });
    if (allEmpty) emptyRowIndices.push(rowIndex);
  });

  // Видаляємо з кінця, щоб не зміщувати індекси попередніх рядків
  for (let i = emptyRowIndices.length - 1; i >= 0; i--) {
    requests.push({
      deleteTableRow: {
        tableCellLocation: {
          tableStartLocation: { index: tableStartIndex },
          rowIndex: emptyRowIndices[i],
          columnIndex: 0,
        },
      },
    });
  }
}

// DEBUG — видалити після перевірки
const _tables = content.filter(el => el.table);
const _debugRows = _tables.map((el, ti) => ({
  tableIndex: ti,
  tableStartIndex: el.startIndex,
  rowCount: el.table.tableRows.length,
  rows: el.table.tableRows.map((row, ri) => ({
    rowIndex: ri,
    cells: row.tableCells.map(cell =>
      (cell.content || [])
        .flatMap(p => (p.paragraph?.elements || []))
        .map(e => e.textRun?.content || '')
        .join('')
        .trim()
    ),
  })),
}));

return [{ json: { docId, ...calc, requests, _debug_empty_rows: { tables_count: _tables.length, requests_count: requests.length, tables: _debugRows } } }];
`.trim();

const buildDocsCode = `
const calc  = $('Code: Після гілки зображення').first().json;
const docId = $('Drive: Копіювати шаблон').first().json.id;
const vars  = calc.template_vars;

const requests = Object.entries(vars).map(([tag, value]) => ({
  replaceAllText: {
    containsText: { text: tag, matchCase: true },
    replaceText:  String(value ?? ''),
  }
}));

return [{
  json: {
    docId,
    requests,
    chat_id:       calc.chat_id,
    file_name:     calc.file_name,
    project_name:  calc.project_name,
    power_label:   calc.power_label,
    total_display: calc.total_display,
    currency_sign: calc.currency_sign,
    driveFolderId: calc.driveFolderId,
  }
}];
`.trim();

const removeTab1Code = `
// Google Docs з вкладками: контент у tabs[0].documentTab.body.content
// Або у body.content для старих документів
const tab0Content = $json.tabs?.[0]?.documentTab?.body?.content || [];
const bodyContent = $json.body?.content || [];
const content = tab0Content.length > 0 ? tab0Content : bodyContent;

let startIndex = null;
let endIndex   = null;

for (let i = 0; i < content.length; i++) {
  const el = content[i];
  if (!el.paragraph || !el.paragraph.elements) continue;
  const text = el.paragraph.elements
    .map(e => (e.textRun?.content || '').trim().toLowerCase())
    .join('');
  if (text === 'вкладка 1') {
    startIndex = el.startIndex;
  } else if (startIndex !== null && text !== '') {
    endIndex = el.startIndex;
    break;
  }
}

const calc  = $('Code: Після гілки зображення').first().json;
const docId = $('Drive: Копіювати шаблон').first().json.id;

const deleteRequests = (startIndex !== null && endIndex !== null)
  ? [{ deleteContentRange: { range: { startIndex, endIndex: endIndex - 1 } } }]
  : [];

return [{ json: { docId, deleteRequests, ...calc } }];
`.trim();

// ── Налаштування (змінити після імпорту) ──────────────────────────
const SPREADSHEET_ID = '1IgaI0_eE0xY7ljfNh138CA-aYIiFzGJpmu9s2hLV04g';
const SHEETS_CRED    = 'Google Sheets account';
const DRIVE_CRED     = 'Google Drive account';
const OAUTH_CRED     = 'Google OAuth2 account';
const TG_CRED        = 'Telegram account';

// ── Вузли ─────────────────────────────────────────────────────────
const nodes = [
  {
    parameters: {
      httpMethod: 'POST',
      path: 'ses-kp',
      responseMode: 'immediatelyReturn',
      options: {}
    },
    id: 'n01', name: 'Webhook',
    type: 'n8n-nodes-base.webhook', typeVersion: 2,
    position: [240, 300], webhookId: 'ses-kp-webhook-id'
  },
  {
    parameters: {
      operation: 'read',
      documentId: { __rl: true, value: SPREADSHEET_ID, mode: 'id' },
      sheetName:  { __rl: true, value: 'Довідкові дані', mode: 'name' },
      options: { range: 'A1:O200', firstRowIsColumnNames: false }
    },
    id: 'n02', name: 'SheetsData',
    type: 'n8n-nodes-base.googleSheets', typeVersion: 4,
    position: [460, 300],
    credentials: { googleSheetsOAuth2Api: { id: 'CRED1', name: SHEETS_CRED } }
  },
  {
    parameters: { mode: 'runOnceForAllItems', jsCode: calculateCode },
    id: 'n04', name: 'Code: Calculate',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [720, 300]
  },
  {
    parameters: { mode: 'runOnceForAllItems', jsCode: chartsCode },
    id: 'n05', name: 'Code: Charts',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [960, 300]
  },
  {
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' },
        conditions: [{
          id: 'cond1',
          leftValue: '={{ $json.has_custom_image }}',
          rightValue: true,
          operator: { type: 'boolean', operation: 'true', name: 'filter.operator.true' }
        }],
        combinator: 'and'
      }
    },
    id: 'n06', name: 'IF: Є зображення',
    type: 'n8n-nodes-base.if', typeVersion: 2,
    position: [1200, 300]
  },
  {
    parameters: { mode: 'runOnceForAllItems', jsCode: uploadCode },
    id: 'n07', name: 'Code: Підготовка зображення',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [1440, 160]
  },
  {
    parameters: {
      resource: 'file',
      operation: 'upload',
      name: '={{ $json.image_file_name }}',
      driveId:  { __rl: true, value: 'MyDrive', mode: 'list' },
      folderId: { __rl: true, value: "={{ $('Code: Calculate').first().json.driveFolderId }}", mode: 'id' },
      binaryPropertyName: 'customImage',
      options: {}
    },
    id: 'n08', name: 'Drive: Upload Custom Image',
    type: 'n8n-nodes-base.googleDrive', typeVersion: 3,
    position: [1680, 160],
    credentials: { googleDriveOAuth2Api: { id: 'CRED2', name: DRIVE_CRED } }
  },
  {
    parameters: {
      method: 'POST',
      url: '=https://www.googleapis.com/drive/v3/files/{{ $json.id }}/permissions',
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleDriveOAuth2Api',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: '{"role":"reader","type":"anyone"}',
      options: { response: { response: { neverError: true } } }
    },
    id: 'n09', name: 'HTTP: Відкрити доступ',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [1920, 160],
    credentials: { googleDriveOAuth2Api: { id: 'CRED2', name: DRIVE_CRED } }
  },
  {
    parameters: { mode: 'runOnceForAllItems', jsCode: afterBranchCode },
    id: 'n10', name: 'Code: Після гілки зображення',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [2160, 300]
  },
  {
    parameters: {
      resource: 'file',
      operation: 'copy',
      fileId:   { __rl: true, value: '={{ $json.templateDocId }}', mode: 'id' },
      name: '={{ $json.doc_copy_name }}',
      driveId:  { __rl: true, value: 'MyDrive', mode: 'list' },
      folderId: { __rl: true, value: '={{ $json.driveFolderId }}', mode: 'id' },
      options: {}
    },
    id: 'n11', name: 'Drive: Копіювати шаблон',
    type: 'n8n-nodes-base.googleDrive', typeVersion: 3,
    position: [2400, 300],
    credentials: { googleDriveOAuth2Api: { id: 'CRED2', name: DRIVE_CRED } }
  },
  {
    parameters: {
      method: 'GET',
      url: "={{ 'https://docs.googleapis.com/v1/documents/' + $('Drive: Копіювати шаблон').first().json.id }}",
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleDocsOAuth2Api',
      options: {}
    },
    id: 'n11a', name: 'HTTP: Отримати Doc',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [2640, 300],
    credentials: { googleDocsOAuth2Api: { id: 'CRED3', name: OAUTH_CRED } }
  },
  {
    parameters: { mode: 'runOnceForAllItems', jsCode: removeTab1Code },
    id: 'n11b', name: 'Code: Видалити Вкладку 1',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [2880, 300]
  },
  {
    parameters: {
      method: 'POST',
      url: "={{ 'https://docs.googleapis.com/v1/documents/' + $json.docId + ':batchUpdate' }}",
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleDocsOAuth2Api',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: '={{ { requests: $json.deleteRequests } }}',
      options: { response: { response: { neverError: true } } }
    },
    id: 'n11c', name: 'HTTP: Видалити Вкладку 1',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [3120, 300],
    credentials: { googleDocsOAuth2Api: { id: 'CRED3', name: OAUTH_CRED } }
  },
  {
    parameters: { mode: 'runOnceForAllItems', jsCode: buildDocsCode },
    id: 'n12', name: 'Code: Підготовка Docs',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [3360, 300]
  },
  {
    parameters: {
      method: 'POST',
      url: "=https://docs.googleapis.com/v1/documents/{{ $json.docId }}:batchUpdate",
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleDocsOAuth2Api',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: '={{ { requests: $json.requests } }}',
      options: {}
    },
    id: 'n13', name: 'HTTP: Docs batchUpdate',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [3600, 300],
    credentials: { googleDocsOAuth2Api: { id: 'CRED3', name: OAUTH_CRED } }
  },
  {
    parameters: {
      method: 'GET',
      url: "={{ 'https://docs.googleapis.com/v1/documents/' + $('Code: Підготовка Docs').first().json.docId }}",
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleDocsOAuth2Api',
      options: {}
    },
    id: 'n13a', name: 'HTTP: Отримати Doc після замін',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [3840, 300],
    credentials: { googleDocsOAuth2Api: { id: 'CRED3', name: OAUTH_CRED } }
  },
  {
    parameters: { mode: 'runOnceForAllItems', jsCode: findEmptyRowsCode },
    id: 'n13b', name: 'Code: Знайти порожні рядки',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [4080, 300]
  },
  {
    parameters: {
      method: 'POST',
      url: "={{ 'https://docs.googleapis.com/v1/documents/' + $json.docId + ':batchUpdate' }}",
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleDocsOAuth2Api',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: '={{ { requests: $json.requests } }}',
      options: { response: { response: { neverError: true } } }
    },
    id: 'n13c', name: 'HTTP: Видалити порожні рядки',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [4320, 300],
    credentials: { googleDocsOAuth2Api: { id: 'CRED3', name: OAUTH_CRED } }
  },
  {
    parameters: {
      method: 'GET',
      url: "={{ 'https://docs.google.com/document/d/' + $('Code: Підготовка Docs').first().json.docId + '/export?format=pdf&tab=t.0' }}",
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleOAuth2Api',
      options: {
        response: { response: { responseFormat: 'file', outputPropertyName: 'data' } }
      }
    },
    id: 'n14', name: 'HTTP: Експорт PDF',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [4560, 300],
    credentials: { googleOAuth2Api: { id: 'CRED3', name: OAUTH_CRED } }
  },
  {
    parameters: {
      resource: 'file',
      operation: 'upload',
      name: "={{ $('Code: Підготовка Docs').first().json.file_name }}",
      driveId:  { __rl: true, value: 'MyDrive', mode: 'list' },
      folderId: { __rl: true, value: "={{ $('Code: Підготовка Docs').first().json.driveFolderId }}", mode: 'id' },
      binaryPropertyName: 'data',
      options: {}
    },
    id: 'n15', name: 'Drive: Зберегти PDF',
    type: 'n8n-nodes-base.googleDrive', typeVersion: 3,
    position: [4800, 460],
    credentials: { googleDriveOAuth2Api: { id: 'CRED2', name: DRIVE_CRED } }
  },
  {
    parameters: {
      resource: 'message',
      operation: 'sendDocument',
      chatId: "={{ $('Code: Calculate').first().json.chat_id }}",
      binaryData: true,
      binaryPropertyName: 'data',
      additionalFields: {
        caption: "=КП для {{ $('Code: Calculate').first().json.project_name }} ({{ $('Code: Calculate').first().json.power_label }}) — готово! ✅"
      }
    },
    id: 'n16', name: 'Telegram: Надіслати PDF',
    type: 'n8n-nodes-base.telegram', typeVersion: 1.2,
    position: [4800, 300],
    credentials: { telegramApi: { id: 'CRED4', name: TG_CRED } }
  }
];

// ── З'єднання ─────────────────────────────────────────────────────
const connections = {
  'Webhook':    { main: [[{ node: 'SheetsData',      type: 'main', index: 0 }]] },
  'SheetsData': { main: [[{ node: 'Code: Calculate', type: 'main', index: 0 }]] },
  'Code: Calculate': { main: [[{ node: 'Code: Charts', type: 'main', index: 0 }]] },
  'Code: Charts':    { main: [[{ node: 'IF: Є зображення', type: 'main', index: 0 }]] },
  'IF: Є зображення': { main: [
    [{ node: 'Code: Підготовка зображення',       type: 'main', index: 0 }],
    [{ node: 'Code: Після гілки зображення', type: 'main', index: 0 }]
  ]},
  'Code: Підготовка зображення':  { main: [[{ node: 'Drive: Upload Custom Image', type: 'main', index: 0 }]] },
  'Drive: Upload Custom Image':   { main: [[{ node: 'HTTP: Відкрити доступ',      type: 'main', index: 0 }]] },
  'HTTP: Відкрити доступ':        { main: [[{ node: 'Code: Після гілки зображення', type: 'main', index: 0 }]] },
  'Code: Після гілки зображення': { main: [[{ node: 'Drive: Копіювати шаблон',   type: 'main', index: 0 }]] },
  'Drive: Копіювати шаблон':      { main: [[{ node: 'HTTP: Отримати Doc',           type: 'main', index: 0 }]] },
  'HTTP: Отримати Doc':           { main: [[{ node: 'Code: Видалити Вкладку 1',    type: 'main', index: 0 }]] },
  'Code: Видалити Вкладку 1':     { main: [[{ node: 'HTTP: Видалити Вкладку 1',    type: 'main', index: 0 }]] },
  'HTTP: Видалити Вкладку 1':     { main: [[{ node: 'Code: Підготовка Docs',        type: 'main', index: 0 }]] },
  'Code: Підготовка Docs':        { main: [[{ node: 'HTTP: Docs batchUpdate',        type: 'main', index: 0 }]] },
  'HTTP: Docs batchUpdate':           { main: [[{ node: 'HTTP: Отримати Doc після замін', type: 'main', index: 0 }]] },
  'HTTP: Отримати Doc після замін':   { main: [[{ node: 'Code: Знайти порожні рядки',    type: 'main', index: 0 }]] },
  'Code: Знайти порожні рядки':       { main: [[{ node: 'HTTP: Видалити порожні рядки',  type: 'main', index: 0 }]] },
  'HTTP: Видалити порожні рядки':     { main: [[{ node: 'HTTP: Експорт PDF',              type: 'main', index: 0 }]] },
  'HTTP: Експорт PDF': { main: [[
    { node: 'Telegram: Надіслати PDF', type: 'main', index: 0 },
    { node: 'Drive: Зберегти PDF',     type: 'main', index: 0 }
  ]] }
};

const workflow = {
  name: 'SES — Генератор КП',
  nodes,
  connections,
  active: false,
  settings: { executionOrder: 'v1' },
  versionId: 'ses-kp-v1',
  meta: { templateCredsSetupCompleted: false, instanceId: '' },
  id: 'ses-kp-workflow-001',
  pinData: {}
};

const outPath = path.join(dir, 'workflow_ses.json');
fs.writeFileSync(outPath, JSON.stringify(workflow, null, 2));
console.log('Done! Size:', fs.statSync(outPath).size, 'bytes');

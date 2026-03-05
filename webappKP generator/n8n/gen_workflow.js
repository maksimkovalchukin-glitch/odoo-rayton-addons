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

const imageItems = $('Drive: Upload Custom Image').all();
let customImageDriveId  = null;
let customImageDriveUrl = null;

if (imageItems.length > 0) {
  customImageDriveId  = imageItems[0].json.id;
  customImageDriveUrl = \`https://drive.google.com/uc?export=view&id=\${customImageDriveId}\`;
}

return [{
  json: {
    ...calc,
    custom_image_drive_id:  customImageDriveId,
    custom_image_drive_url: customImageDriveUrl,
  }
}];
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

// ── Налаштування (змінити після імпорту) ──────────────────────────
const SPREADSHEET_ID = 'ПОСТАВТЕ_ID_ТАБЛИЦІ_ТУТ';
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
      options: { range: 'A1:I200' }
    },
    id: 'n02', name: 'SheetsData',
    type: 'n8n-nodes-base.googleSheets', typeVersion: 4,
    position: [460, 180],
    credentials: { googleSheetsOAuth2Api: { id: 'CRED1', name: SHEETS_CRED } }
  },
  {
    parameters: {
      operation: 'read',
      documentId: { __rl: true, value: SPREADSHEET_ID, mode: 'id' },
      sheetName:  { __rl: true, value: 'Довідкові дані', mode: 'name' },
      options: { range: 'O1:O2', firstRowIsColumnNames: false }
    },
    id: 'n03', name: 'SheetsRates',
    type: 'n8n-nodes-base.googleSheets', typeVersion: 4,
    position: [460, 420],
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
      specifyBody: 'string',
      body: '{"role":"reader","type":"anyone"}',
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
    parameters: { mode: 'runOnceForAllItems', jsCode: buildDocsCode },
    id: 'n12', name: 'Code: Підготовка Docs',
    type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [2640, 300]
  },
  {
    parameters: {
      method: 'POST',
      url: "=https://docs.googleapis.com/v1/documents/{{ $json.docId }}:batchUpdate",
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleDocsOAuth2Api',
      sendBody: true,
      specifyBody: 'string',
      body: '={{ JSON.stringify({ requests: $json.requests }) }}',
      options: {}
    },
    id: 'n13', name: 'HTTP: Docs batchUpdate',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [2880, 300],
    credentials: { googleDocsOAuth2Api: { id: 'CRED3', name: OAUTH_CRED } }
  },
  {
    parameters: {
      method: 'GET',
      url: '=https://docs.google.com/document/d/{{ $json.docId }}/export?format=pdf',
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'googleOAuth2Api',
      options: {
        response: { response: { responseFormat: 'file', outputPropertyName: 'data' } }
      }
    },
    id: 'n14', name: 'HTTP: Експорт PDF',
    type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
    position: [3120, 300],
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
    position: [3360, 300],
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
    position: [3600, 300],
    credentials: { telegramApi: { id: 'CRED4', name: TG_CRED } }
  }
];

// ── З'єднання ─────────────────────────────────────────────────────
const connections = {
  'Webhook': { main: [[
    { node: 'SheetsData',  type: 'main', index: 0 },
    { node: 'SheetsRates', type: 'main', index: 0 }
  ]]},
  'SheetsData':  { main: [[{ node: 'Code: Calculate', type: 'main', index: 0 }]] },
  'SheetsRates': { main: [[{ node: 'Code: Calculate', type: 'main', index: 0 }]] },
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
  'Drive: Копіювати шаблон':      { main: [[{ node: 'Code: Підготовка Docs',      type: 'main', index: 0 }]] },
  'Code: Підготовка Docs':        { main: [[{ node: 'HTTP: Docs batchUpdate',      type: 'main', index: 0 }]] },
  'HTTP: Docs batchUpdate':       { main: [[{ node: 'HTTP: Експорт PDF',           type: 'main', index: 0 }]] },
  'HTTP: Експорт PDF':            { main: [[{ node: 'Drive: Зберегти PDF',         type: 'main', index: 0 }]] },
  'Drive: Зберегти PDF':          { main: [[{ node: 'Telegram: Надіслати PDF',     type: 'main', index: 0 }]] }
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

/* ================================================================
   n8n Code Node — Завантаження кастомного зображення в Google Drive

   Запускається після "Code: Charts" лише якщо є custom_image_base64.
   В n8n: використовуй IF вузол перед цим кодом:
     IF {{ $json.has_custom_image }} === true → цей вузол
     ELSE → одразу до "Drive: Copy Template"

   ВХІД:  $('Code: Charts').first().json
   ВИХІД: всі поля + custom_image_drive_id, custom_image_drive_url

   Після цього вузла — вузол "Drive: Upload Image" або
   використовуємо HTTP Request до Drive API напряму.
================================================================ */

const data = $('Code: Charts').first().json;

// Якщо немає зображення — просто пропускаємо (не повинно сюди потрапити через IF)
if (!data.has_custom_image || !data.custom_image_base64) {
  return [{ json: { ...data, custom_image_drive_id: null, custom_image_drive_url: null } }];
}

// Декодуємо base64 → бінарний буфер
const base64 = data.custom_image_base64;
const mime   = data.custom_image_mime || 'image/jpeg';
const ext    = mime.split('/')[1] || 'jpg';
const fileName = `viz_${data.project_name || 'ses'}_${Date.now()}.${ext}`;

// Конвертуємо base64 у Buffer для n8n бінарного виводу
const buffer = Buffer.from(base64, 'base64');

// Повертаємо як бінарні дані — наступний вузол "Drive: Upload" їх завантажить
return [{
  json: {
    ...data,
    image_file_name: fileName,
    image_mime:      mime,
  },
  binary: {
    customImage: {
      data:     base64,
      mimeType: mime,
      fileName: fileName,
    }
  }
}];

/* ================================================================
   ПІСЛЯ ЦЬОГО ВУЗЛА в n8n:

   [Drive: Upload Image]
   - Operation: Upload
   - Parent Folder: {{ $json.driveFolderId }}  (або окрема папка)
   - File Name: {{ $json.image_file_name }}
   - Binary Property: customImage
   → Отримуємо: id, webViewLink, webContentLink

   Потім зберігаємо Drive ID і передаємо далі для вставки в Docs.

   [Code: Merge Image URL]
   const prevData = $('Code: Charts').first().json;  // або передати через попередні
   const driveFile = $('Drive: Upload Image').first().json;
   return [{
     json: {
       ...prevData,
       custom_image_drive_id:  driveFile.id,
       // Drive URL для публічного доступу (файл має бути shared: anyone with link):
       custom_image_drive_url: `https://drive.google.com/uc?export=view&id=${driveFile.id}`,
     }
   }];

   [HTTP: Share Image Publicly]  (зробити файл публічним)
   - Method: POST
   - URL: https://www.googleapis.com/drive/v3/files/{{ $json.custom_image_drive_id }}/permissions
   - Auth: Google OAuth2
   - Body: { "role": "reader", "type": "anyone" }

   Після цього — вставляємо зображення в Doc через insertInlineImage.
================================================================ */

// Снимок с телефона весит 3–8 МБ. Для отчёта хватает 1280 px по длинной стороне:
// пережимаем в JPEG, иначе демо-хранилище браузера (≈5 МБ) кончится на втором фото.
export async function compressImage(file: File, maxSide = 1280, quality = 0.82): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Браузер не умеет обрабатывать изображения');
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.toDataURL('image/jpeg', quality);
}

import type { IIncident } from '../types';
import { getPrimaryResponsible, getRecidivismCount } from './responsibles';

/**
 * Вспомогательная функция для асинхронного скачивания локального шрифта и конвертации в Base64
 */
const fetchLocalFontAsBase64 = async (url: string): Promise<string> => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(
      `Не удалось найти файл шрифта в папке public/. Убедитесь, что положили туда PT-Sans-Regular.ttf`
    );
  }
  
  const blob = await response.blob();
  
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = reader.result as string;
      const base64Content = dataUrl.split(',');
      resolve(base64Content[1]); // Берем чистый контент Base64
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
};

export const generateKnmAct = async (incident: IIncident) => {
  // jsPDF тяжёлый (~400 КБ с html2canvas) — тянем его только при выгрузке акта
  const { jsPDF } = await import('jspdf');
  const currentDate = new Date().toLocaleDateString('ru-RU');
  const primary = getPrimaryResponsible(incident);
  const orgName = primary?.organization.name ?? 'не определена';
  const directorName = primary?.organization.directorName ?? 'не указан';
  const recidivism = getRecidivismCount(incident);

  try {
    const localFontUrl = '/fonts/PT-Sans-Regular.ttf';
    const fontBase64 = await fetchLocalFontAsBase64(localFontUrl);
    const fontFileName = '/fonts/PT-Sans-Regular.ttf';


    // ДОКУМЕНТ 1: ОФИЦИАЛЬНЫЙ АКТ ОСМОТРА ТЕРРИТОРИИ
 
    const actDoc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    
    // Регистрируем и активируем кириллицу для Акта
    actDoc.addFileToVFS(fontFileName, fontBase64);
    actDoc.addFont(fontFileName, 'PT-Sans', 'normal');
    actDoc.setFont('PT-Sans', 'normal');

    // Шапка Министерства / Инспекции
    actDoc.setFontSize(10);
    actDoc.text('ДЕПАРТАМЕНТ РАЗВИТИЯ ТЕРРИТОРИИ АДМИНИСТРАЦИИ Г. ЛИПЕЦКА', 105, 15, { align: 'center' });
    actDoc.setFontSize(9);
    actDoc.text('г. Липецк, ул. Советская, д. 3', 105, 20, { align: 'center' });
    actDoc.line(20, 23, 190, 23);

    // Заголовки Акта
    actDoc.setFontSize(14);
    actDoc.text(`АКТ ИНСПЕКЦИИ № КНМ-${incident.id}`, 105, 35, { align: 'center' });
    actDoc.setFontSize(10);
    actDoc.text('о выявлении нарушения обязательных требований по благоустройству ТКО', 105, 41, { align: 'center' });

    actDoc.text(`Дата составления: ${currentDate} г.`, 20, 52);
    actDoc.text('Место составления: г. Липецк', 190, 52, { align: 'right' });

    let y = 65;
    actDoc.text('Настоящий акт составлен инспекцией ДРТ на основании данных автоматизированной системы ИИ.', 20, y); y += 6;
    actDoc.text('В ходе мониторинга городской территории зафиксировано нарушение правил содержания площадки.', 20, y); y += 12;

    actDoc.setFontSize(11);
    actDoc.text('ДЕТАЛИЗАЦИЯ ПРАВОНАРУШЕНИЯ:', 20, y); y += 6;
    actDoc.setFontSize(10);
    actDoc.text(`1. Уникальный идентификатор дела: № ${incident.id}`, 20, y); y += 6;
    
    const splitAddress = actDoc.splitTextToSize(`2. Адрес расположения объекта: г. Липецк, ${incident.location.address}`, 160);
    actDoc.text(splitAddress, 20, y); 
    y += (splitAddress.length * 6);

    actDoc.text(`3. Кадастровый номер земельного участка: ${incident.location.cadastralNumber || 'Не определен'}`, 20, y); y += 6;
    actDoc.text(`4. Первичный источник сигнала нарушения: ${incident.source}`, 20, y); y += 6;
    actDoc.text(`5. Дата фиксации нарушения нейросетью: ${new Date(incident.timeline.createdAt).toLocaleString('ru-RU')}`, 20, y); y += 6;
    actDoc.text(`6. Регламентный срок (SLA) на добровольную уборку: ИСТЕК`, 20, y); y += 12;

    actDoc.setFontSize(11);
    actDoc.text('СВЕДЕНИЯ ОБ ОТВЕТСТВЕННОМ ЛИЦЕ:', 20, y); y += 6;
    actDoc.setFontSize(10);
    actDoc.text(`Управляющая организация (Балансодержатель): ${orgName}`, 20, y); y += 6;
    actDoc.text(`Ответственный руководитель: ${directorName}`, 20, y); y += 6;
    actDoc.text(`Статистика повторности (Рецидивов) по адресу: ${recidivism}-й случай за месяц.`, 20, y); y += 12;

    actDoc.text('ЗАКЛЮЧЕНИЕ И НАДЗОРНЫЙ КОНТУР:', 20, y); y += 6;
    const splitConclusion = actDoc.splitTextToSize('Учитывая, что Управляющая компания просрочила регламентные сроки SLA оперативного реагирования и на момент истечения таймера не предоставила фотоотчет, материалы дела направляются в ГЖИ для возбуждения административного производства.', 160);
    actDoc.text(splitConclusion, 20, y);
    y += (splitConclusion.length * 6) + 20;

    actDoc.text('Подпись ответственного инспектора ДРТ: _______________________ (Алексей ДРТ)', 20, y);

    // Скачиваем Акт
    actDoc.save(`1_Акт_Осмотра_ДРТ_№_${incident.id}.pdf`);

    // ДОКУМЕНТ 2: ОФИЦИАЛЬНОЕ ПРЕДПИСАНИЕ НА ЛИКВИДАЦИЮ ДЛЯ УК

    const orderDoc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    
    // Повторно регистрируем и включаем шрифт для второго независимого бланка
    orderDoc.addFileToVFS(fontFileName, fontBase64);
    orderDoc.addFont(fontFileName, 'PT-Sans', 'normal');
    orderDoc.setFont('PT-Sans', 'normal');

    // Шапка ведомства
    orderDoc.setFontSize(10);
    orderDoc.text('ДЕПАРТАМЕНТ РАЗВИТИЯ ТЕРРИТОРИИ АДМИНИСТРАЦИИ Г. ЛИПЕЦКА', 105, 15, { align: 'center' });
    orderDoc.line(20, 23, 190, 23);

    // Заголовки Предписания
    orderDoc.setFontSize(14);
    orderDoc.text(`ОФИЦИАЛЬНОЕ ПРЕДПИСАНИЕ № П-SLA-${incident.id}`, 105, 35, { align: 'center' });
    
    orderDoc.setFontSize(10);
    orderDoc.text(`Кому: Руководству ${orgName} (${directorName})`, 20, 45);
    orderDoc.text(`От кого: Руководитель Территориальной Управы Округа №${incident.location.upravaId || '3'}`, 20, 51);
    orderDoc.line(20, 55, 190, 55);

    let y2 = 65;
    orderDoc.setFontSize(12);
    orderDoc.text('ТРЕБОВАНИЕ ОБ УСТРАНЕНИИ НАРУШЕНИЙ БЛАГОУСТРОЙСТВА', 20, y2); y2 += 8;
    
    orderDoc.setFontSize(10);
    const splitOrderText = orderDoc.splitTextToSize(`На основании данных автоматизированного контроля, Вам необходимо в срочном внеочередном порядке организовать работы по уборке контейнерной площадки и ликвидации навалов мусора по адресу:`, 160);
    orderDoc.text(splitOrderText, 20, y2);
    y2 += (splitOrderText.length * 6) + 4;

    // Выделяем адрес жирным визуальным отступом
    orderDoc.text(`👉 ЦЕЛЕВОЙ АДРЕС: г. Липецк, ${incident.location.address}`, 25, y2); y2 += 8;
    
    orderDoc.text(`Внимание: по данному участку зафиксирован ${recidivism}-й случай повторного рецидива за текущий месяц.`, 20, y2); y2 += 8;
    
    const splitWarning = orderDoc.splitTextToSize('В случае невыполнения настоящего законного требования в установленный регламентом срок, материалы дела будут автоматически переданы в Государственную жилищную инспекцию (ГЖИ) Липецкой области для наложения штрафных санкций и принудительного взыскания через суд.', 160);
    orderDoc.text(splitWarning, 20, y2);
    y2 += (splitWarning.length * 6) + 25;

    orderDoc.text('Служащий руководитель Управы ДРТ: _______________________ (Управа Липецк)', 20, y2);

    // Скачиваем Предписание
    orderDoc.save(`2_Предписание_для_УК_№_${incident.id}.pdf`);

  } catch (error) {
    console.error('Ошибка пакетной генерации документов ДРТ:', error);
  }
};

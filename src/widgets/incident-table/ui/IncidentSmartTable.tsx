import React, { useState } from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { getStatusBadge } from '@/entities/incident/lib/cardUtils'; // Твоя утилита бейджей!
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Search, AlertCircle, Calendar, Building2 } from 'lucide-react';

export const IncidentSmartTable: React.FC = () => {
  // 1. Достаем массив инцидентов и управление выбором из нашего Zustand-стора
  const { incidents, selectedIncident, selectIncident } = useIncidentStore();
  
  // ЛОКАЛЬНЫЕ СТЕЙТЫ ДЛЯ РАСШИРЕННОЙ ФИЛЬТРАЦИИ
  const [searchQuery, setSearchQuery] = useState<string>(''); // поиск по адресу
  const [searchUk, setSearchUk] = useState<string>('');       // поиск по названию УК (Новое!)
  const [selectedUprava, setSelectedUprava] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all'); // фильтр по статусу (Новое!)
  const [selectedDateFilter, setSelectedDateFilter] = useState<string>('all'); // фильтр по дате (Новое!)

  // Генерируем массив из 19 управ для выпадающего списка согласно регламенту ДРТ
  const lipetskUpravas = Array.from({ length: 19 }, (_, i) => i + 1);

  // СКВОЗНАЯ ФИЛЬТРАЦИЯ: Фильтруем одновременно по пяти ведомственным параметрам
  const filteredIncidents = incidents.filter((incident) => {
    // 1. Проверка по адресу
    const matchesSearch = incident.location.address.toLowerCase().includes(searchQuery.toLowerCase());
    
    // 2. Проверка по названию ответственной УК
    const matchesUk = incident.responsible.organizationName.toLowerCase().includes(searchUk.toLowerCase());
    
    // 3. Проверка по 19 Управам Липецка
    const matchesUprava = selectedUprava === 'all' || incident.location.upravaId === Number(selectedUprava);
    
    // 4. Проверка по Стадиям ведомственного контроля
    const matchesStatus = selectedStatus === 'all' || incident.status === selectedStatus;
    
    // 5. Проверка по Дате регистрации инцидента
    let matchesDate = true;
    if (selectedDateFilter !== 'all') {
      const createdAt = new Date(incident.timeline.createdAt).getTime();
      const now = Date.now();
      const oneDayMs = 24 * 60 * 60 * 1000;

      if (selectedDateFilter === 'today') {
        const createdDateStr = new Date(incident.timeline.createdAt).toDateString();
        const nowDateStr = new Date().toDateString();
        matchesDate = createdDateStr === nowDateStr;
      } else if (selectedDateFilter === '3days') {
        matchesDate = (now - createdAt) <= (3 * oneDayMs);
      } else if (selectedDateFilter === 'week') {
        matchesDate = (now - createdAt) <= (7 * oneDayMs);
      }
    }
    
    return matchesSearch && matchesUk && matchesUprava && matchesStatus && matchesDate;
  });

  return (
    <div className="flex flex-col gap-4 bg-white border border-slate-200 rounded-xl p-4 shadow-sm w-full">
      
      {/* МОДЕРНИЗИРОВАННАЯ ВЕДОМСТВЕННАЯ ПАНЕЛЬ ФИЛЬТРАЦИИ ДРТ */}
      <div className="flex flex-col gap-3 w-full border-b border-slate-100 pb-3">
        
        {/* СТРОКА 1: Текстовый поиск по адресам и Управляющим компаниям */}
        <div className="flex flex-col md:flex-row gap-3 w-full">
          {/* Текстовый поиск по улицам */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Поиск по адресу нарушения (например, Космонавтов)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9 text-xs focus-visible:ring-blue-600 w-full"
            />
          </div>

          {/* Текстовый поиск по названию УК */}
          <div className="relative flex-1">
            <Building2 className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Поиск по названию ответственной УК..."
              value={searchUk}
              onChange={(e) => setSearchUk(e.target.value)}
              className="pl-9 h-9 text-xs focus-visible:ring-blue-600 w-full"
            />
          </div>
        </div>

        {/* СТРОКА 2: Выпадающие селекторы (Управы, Статусы, Сроки) */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 w-full">
          
          {/* СУВЕРЕННЫЙ СЕЛЕКТОР 19 УПРАВ ЛИПЕЦКА */}
          <Select value={selectedUprava} onValueChange={setSelectedUprava}>
            <SelectTrigger className="w-56 h-9 text-xs font-semibold text-slate-700 bg-slate-50 border-slate-200 focus:ring-blue-600">
              <div className="flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-slate-400" />
                <SelectValue placeholder="Выбор округа" />
              </div>
            </SelectTrigger>
            <SelectContent className="bg-white border-slate-200">
              <SelectItem value="all" className="text-xs font-bold text-slate-700 focus:bg-slate-50">
                Все 19 Управ города
              </SelectItem>
              {lipetskUpravas.map((num) => (
                <SelectItem key={num} value={String(num)} className="text-xs font-medium text-slate-600 focus:bg-slate-50">
                  Управа Округа №{num}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* СЕЛЕКТОР СТАДИЙ КОНТРОЛЯ */}
          <Select value={selectedStatus} onValueChange={setSelectedStatus}>
            <SelectTrigger className="w-48 h-9 text-xs font-semibold text-slate-700 bg-slate-50 border-slate-200 focus:ring-blue-600">
              <div className="flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 text-slate-400" />
                <SelectValue placeholder="Текущий статус" />
              </div>
            </SelectTrigger>
            <SelectContent className="bg-white border-slate-200">
              <SelectItem value="all" className="text-xs font-bold text-slate-700 focus:bg-slate-50">Все статусы контроля</SelectItem>
              <SelectItem value="NEW" className="text-xs text-blue-600 font-semibold focus:bg-slate-50">Новые инциденты</SelectItem>
              <SelectItem value="IN_PROGRESS" className="text-xs text-amber-600 font-semibold focus:bg-slate-50">В работе у УК (SLA)</SelectItem>
              <SelectItem value="VERIFICATION" className="text-xs text-purple-500 font-semibold focus:bg-slate-50">На верификации</SelectItem>
              <SelectItem value="KNM_ESCALATION" className="text-xs text-rose-600 font-semibold focus:bg-slate-50">Эскалация в КНМ</SelectItem>
              <SelectItem value="CLOSED" className="text-xs text-emerald-500 font-semibold focus:bg-slate-50">Нарушение устранено</SelectItem>
            </SelectContent>
          </Select>

          {/* СЕЛЕКТОР ДАТЫ ПОСТУПЛЕНИЯ (Новое!) */}
          <Select value={selectedDateFilter} onValueChange={setSelectedDateFilter}>
            <SelectTrigger className="w-44 h-9 text-xs font-semibold text-slate-700 bg-slate-50 border-slate-200 focus:ring-blue-600">
              <div className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <SelectValue placeholder="Дата поступления" />
              </div>
            </SelectTrigger>
            <SelectContent className="bg-white border-slate-200">
              <SelectItem value="all" className="text-xs font-bold text-slate-700 focus:bg-slate-50">📅 За всё время</SelectItem>
              <SelectItem value="today" className="text-xs font-medium text-slate-600 focus:bg-slate-50">За сегодня</SelectItem>
              <SelectItem value="3days" className="text-xs font-medium text-slate-600 focus:bg-slate-50">За последние 3 дня</SelectItem>
              <SelectItem value="week" className="text-xs font-medium text-slate-600 focus:bg-slate-50">За неделю</SelectItem>
            </SelectContent>
          </Select>

          {/* Динамический счетчик отфильтрованных инцидентов */}
          <div className="ml-auto text-[10px] text-slate-400 font-bold uppercase tracking-wider bg-slate-50 px-2.5 py-1.5 rounded-md border border-slate-100 whitespace-nowrap">
            Активных дел в контуре: <span className="text-slate-700 font-black">{filteredIncidents.length}</span>
          </div>
        </div>
      </div>

      {/* ТАБЛИЧНАЯ СЕТКА */}
      <div className="border border-slate-100 rounded-lg overflow-hidden w-full">
        <Table>
          <TableHeader className="bg-slate-50/70 text-slate-400">
            <TableRow className="hover:bg-transparent border-slate-100">
              <TableHead className="w-20 text-xs font-bold uppercase tracking-wider text-slate-500 h-9">ID</TableHead>
              <TableHead className="text-xs font-bold uppercase tracking-wider text-slate-500 h-9">Адрес объекта благоустройства</TableHead>
              <TableHead className="text-xs font-bold uppercase tracking-wider text-slate-500 h-9">Текущий Статус</TableHead>
              <TableHead className="text-xs font-bold uppercase tracking-wider text-slate-500 h-9">Ответственная УК</TableHead>
              <TableHead className="text-xs font-bold uppercase tracking-wider text-slate-500 h-9">Повторность</TableHead>
              <TableHead className="text-xs font-bold uppercase tracking-wider text-slate-500 h-9 text-right">Поступление</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredIncidents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-xs text-slate-400 font-medium">
                  <div className="flex flex-col items-center justify-center gap-1.5">
                    <AlertCircle className="w-5 h-5 text-slate-300 stroke-1.5" />
                    <span>По вашему поисковому запросу инцидентов в Липецке не найдено</span>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              filteredIncidents.map((incident) => {
                const isSelected = selectedIncident?.id === incident.id;
                
                return (
                  <TableRow
                    key={incident.id}
                    onClick={() => selectIncident(incident.id)}
                    className={`cursor-pointer transition-colors border-slate-100/60 ${
                      isSelected 
                        ? 'bg-blue-50/50 hover:bg-blue-50/70 border-l-4 border-l-blue-600 font-medium' 
                        : 'hover:bg-slate-50/50'
                    }`}
                  >
                    {/* ID дела */}
                    <TableCell className="font-mono text-xs font-bold text-slate-500">
                      #{incident.id}
                    </TableCell>
                    
                    {/* Адрес */}
                    <TableCell className="text-xs font-semibold text-slate-700">
                      {incident.location.address}
                    </TableCell>
                    
                    {/* Статус ведомственного контроля */}
                    <TableCell className="h-9 py-1">
                      {getStatusBadge(incident.status)}
                    </TableCell>
                    
                    {/* Ответственная организация */}
                    <TableCell className="text-xs text-slate-600 font-medium">
                      {incident.responsible.organizationName}
                    </TableCell>
                    
                    {/* Метрика рецидивов */}
                    <TableCell className="text-xs font-medium">
                      <span className={`px-2 py-0.5 rounded-sm text-[10px] font-bold ${
                        incident.responsible.recidivismCount > 2 
                          ? 'bg-rose-50 text-rose-600 border border-rose-100' 
                          : 'bg-slate-100 text-slate-600'
                      }`}>
                        {incident.responsible.recidivismCount}-й инцидент
                      </span>
                    </TableCell>
                    
                    {/* Дата поступления сигнала ИИ */}
                    <TableCell className="text-right text-xs text-slate-400 font-medium">
                      <span className="inline-flex items-center gap-1">
                        <Calendar className="w-3 h-3 stroke-1.5" />
                        {new Date(incident.timeline.createdAt).toLocaleDateString('ru-RU')}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

    </div>
  );
};

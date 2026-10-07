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
  
// Локальные стейты для текстового поиска и фильтрации по 19 Управам
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedUprava, setSelectedUprava] = useState<string>('all');

  // Генерируем массив из 19 управ для выпадающего списка согласно регламенту ДРТ
  const lipetskUpravas = Array.from({ length: 19 }, (_, i) => i + 1);

  // 🔍 СКВОЗНАЯ ФИЛЬТРАЦИЯ: Фильтруем одновременно и по тексту, и по номеру ведомственной управы
  const filteredIncidents = incidents.filter((incident) => {
    const matchesSearch = incident.location.address.toLowerCase().includes(searchQuery.toLowerCase());
    
    // Если выбрано "all" — пропускаем все, если конкретное число — сверяем с upravaId
    const matchesUprava = selectedUprava === 'all' || incident.location.upravaId === Number(selectedUprava);
    
    return matchesSearch && matchesUprava;
  });

  return (
    <div className="flex flex-col gap-4 bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      
      {/* 🎛️ ВЕДОМСТВЕННАЯ ПАНЕЛЬ ФИЛЬТРАЦИИ ДРТ */}
      <div className="flex items-center justify-between gap-4 flex-wrap w-full">
        <div className="flex flex-1 items-center gap-3 min-w-75">
          
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

          {/* 🏢 СУВЕРЕННЫЙ СЕЛЕКТОР 19 УПРАВ ЛИПЕЦКА */}
          <Select value={selectedUprava} onValueChange={setSelectedUprava}>
            <SelectTrigger className="w-56 h-9 text-xs font-semibold text-slate-700 bg-slate-50 border-slate-200 focus:ring-blue-600">
              <div className="flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-slate-400" />
                <SelectValue placeholder="Выбор округа" />
              </div>
            </SelectTrigger>
            <SelectContent className="bg-white border-slate-200">
              <SelectItem value="all" className="text-xs font-bold text-slate-700 focus:bg-slate-50">
                🌍 Все 19 Управ города
              </SelectItem>
              {lipetskUpravas.map((num) => (
                <SelectItem key={num} value={String(num)} className="text-xs font-medium text-slate-600 focus:bg-slate-50">
                  🏢 Управа Округа №{num}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

        </div>

        <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider bg-slate-50 px-2.5 py-1.5 rounded-md border border-slate-100 whitespace-nowrap">
          Активных дел в контуре: <span className="text-slate-700 font-black">{filteredIncidents.length}</span>
        </div>
      </div>

      {/* 📋 ТАБЛИЧНАЯ СЕТКА */}
      <div className="border border-slate-100 rounded-lg overflow-hidden">
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

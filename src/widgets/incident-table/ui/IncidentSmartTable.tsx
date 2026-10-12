import React from 'react';
import { useIncidentStore } from '@/entities/incident/model/incidentStore';
import { useFilterStore, useFilteredIncidents, type IncidentFilters, type PeriodFilter } from '@/entities/incident/model/filterStore';
import { getStatusBadge } from '@/entities/incident/lib/cardUtils';
import { getPrimaryOrganizationName, getRecidivismCount } from '@/entities/incident/lib/responsibles';
import { STATUS_META, STATUS_ORDER, formatDate, formatDateTime, typoQuotes } from '@/entities/incident/lib/presentation';
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
import { Search, Building2 } from 'lucide-react';

const FILTER_TRIGGER = 'h-10 w-full bg-card text-[14px] sm:w-auto sm:min-w-48';
const FILTER_ITEM = 'text-[14px]';
const TH = 'h-10 text-[13px] font-medium text-muted-foreground';

export const IncidentSmartTable: React.FC = () => {
  const { selectedIncident, selectIncident } = useIncidentStore();

  // Фильтры общие с картой и лентами других тем — стор filterStore
  const filters = useFilterStore();
  const filteredIncidents = useFilteredIncidents();

  // 19 управ Липецка для выпадающего списка согласно регламенту ДРТ
  const lipetskUpravas = Array.from({ length: 19 }, (_, i) => i + 1);

  return (
    <section className="flex w-full shrink-0 flex-col rounded-lg border border-border bg-card">
      <div className="flex items-baseline justify-between gap-4 border-b border-border px-5 py-3">
        <h2 className="text-[16px] font-semibold text-foreground">Реестр обращений</h2>
        <span className="text-[14px] text-muted-foreground">
          Найдено: <span className="font-medium text-foreground">{filteredIncidents.length}</span>
        </span>
      </div>

      {/* Фильтры */}
      <div className="flex flex-col gap-3 border-b border-border px-5 py-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="relative">
            <Search className="absolute left-3 top-3 size-4 text-muted-foreground" />
            <Input
              placeholder="Адрес, например «Космонавтов»"
              value={filters.query}
              onChange={(e) => filters.set({ query: e.target.value })}
              className="h-10 pl-9 text-[14px]"
              aria-label="Поиск по адресу"
            />
          </div>
          <div className="relative">
            <Building2 className="absolute left-3 top-3 size-4 text-muted-foreground" />
            <Input
              placeholder="Ответственная организация"
              value={filters.org}
              onChange={(e) => filters.set({ org: e.target.value })}
              className="h-10 pl-9 text-[14px]"
              aria-label="Поиск по ответственной организации"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <Select value={filters.uprava} onValueChange={(v) => filters.set({ uprava: v })}>
            <SelectTrigger className={FILTER_TRIGGER} aria-label="Управа">
              <SelectValue placeholder="Управа" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className={FILTER_ITEM}>Все управы</SelectItem>
              {lipetskUpravas.map((num) => (
                <SelectItem key={num} value={String(num)} className={FILTER_ITEM}>
                  Управа округа № {num}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={filters.status} onValueChange={(v) => filters.set({ status: v as IncidentFilters['status'] })}>
            <SelectTrigger className={FILTER_TRIGGER} aria-label="Статус">
              <SelectValue placeholder="Статус" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className={FILTER_ITEM}>Все статусы</SelectItem>
              {STATUS_ORDER.map((status) => (
                <SelectItem key={status} value={status} className={FILTER_ITEM}>
                  {STATUS_META[status].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={filters.period} onValueChange={(v) => filters.set({ period: v as PeriodFilter })}>
            <SelectTrigger className={FILTER_TRIGGER} aria-label="Период поступления">
              <SelectValue placeholder="Период" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className={FILTER_ITEM}>За всё время</SelectItem>
              <SelectItem value="today" className={FILTER_ITEM}>За сегодня</SelectItem>
              <SelectItem value="3days" className={FILTER_ITEM}>За 3 дня</SelectItem>
              <SelectItem value="week" className={FILTER_ITEM}>За неделю</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Table>
        <TableHeader className="bg-muted">
          <TableRow className="hover:bg-transparent">
            <TableHead className={`${TH} w-20 pl-5`}>№</TableHead>
            <TableHead className={TH}>Адрес</TableHead>
            <TableHead className={TH}>Статус</TableHead>
            <TableHead className={TH}>Ответственный</TableHead>
            <TableHead className={`${TH} text-right`}>Раз за месяц</TableHead>
            <TableHead className={`${TH} pr-5 text-right`}>Поступило</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filteredIncidents.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="h-24 text-center text-[14px] text-muted-foreground">
                Обращений с такими условиями нет. Измените фильтры.
              </TableCell>
            </TableRow>
          ) : (
            filteredIncidents.map((incident) => {
              const isSelected = selectedIncident?.id === incident.id;
              const repeats = getRecidivismCount(incident);

              return (
                <TableRow
                  key={incident.id}
                  onClick={() => selectIncident(incident.id)}
                  aria-selected={isSelected}
                  className={`h-12 cursor-pointer text-[14px] ${
                    isSelected
                      ? 'bg-secondary shadow-[inset_3px_0_0_var(--primary)] hover:bg-secondary'
                      : 'hover:bg-muted'
                  }`}
                >
                  <TableCell className="pl-5 text-muted-foreground">{incident.id}</TableCell>
                  <TableCell className="whitespace-normal font-medium text-foreground">
                    {incident.location.address}
                  </TableCell>
                  <TableCell>{getStatusBadge(incident.status)}</TableCell>
                  <TableCell className="text-foreground">
                    {typoQuotes(getPrimaryOrganizationName(incident))}
                  </TableCell>
                  <TableCell
                    className={`text-right ${repeats > 2 ? 'font-semibold text-danger' : 'text-foreground'}`}
                  >
                    {repeats > 0 ? repeats : '—'}
                  </TableCell>
                  <TableCell
                    className="pr-5 text-right text-muted-foreground"
                    title={formatDateTime(incident.timeline.createdAt)}
                  >
                    {formatDate(incident.timeline.createdAt)}
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </section>
  );
};

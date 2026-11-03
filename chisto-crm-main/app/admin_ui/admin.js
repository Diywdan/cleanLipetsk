// Консоль системного администратора CRM «Чистый Липецк» (/admin/).
// Без сборки и зависимостей: страница ходит в API CRM (/api/v1) с той же кукой сессии, что и
// «Диспетчерская». Разделы показываются по правам пользователя, права проверяет сервер.
'use strict';

(() => {
  const API = '/api/v1';
  const TZ = 'Europe/Moscow';

  // ── Мелочи ──────────────────────────────────────────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const sum = (obj) => Object.values(obj || {}).reduce((a, b) => a + (Number(b) || 0), 0);
  const plural = (n, one, few, many) => {
    const m10 = n % 10, m100 = n % 100;
    return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
  };
  const dtf = new Intl.DateTimeFormat('ru-RU', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  const fmt = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? esc(iso) : dtf.format(d).replace(',', '');
  };
  const fmtDay = (s) => (s ? esc(String(s).split('-').reverse().join('.')) : '—');
  const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: TZ });
  const none = (text = 'нет') => `<span class="none">${esc(text)}</span>`;

  // ── Справочники подписей ───────────────────────────────────────────────
  const EVENT_STATUS = {
    RECEIVED: ['Ждёт разбора', 'info'],
    PROCESSED: ['Дело создано', 'ok'],
    NEEDS_REVIEW: ['Дело создано, есть расхождения', 'warn'],
    FAILED: ['Ошибка разбора', 'bad'],
  };
  const CASE_STATUS = {
    NEW: ['Новое', 'info'],
    IN_PROGRESS: ['В работе', 'warn'],
    VERIFICATION: ['На проверке', 'violet'],
    KNM_ESCALATION: ['КНМ', 'bad'],
    CLOSED: ['Закрыто', 'ok'],
  };
  const CASE_COLORS = { NEW: 'var(--primary)', IN_PROGRESS: 'var(--warning)', VERIFICATION: 'var(--violet)', KNM_ESCALATION: 'var(--danger)', CLOSED: 'var(--success)' };
  const REG_STATUS = {
    pending_review: ['На разборе', 'warn'],
    registered: ['Привязан', 'ok'],
    already_registered: ['Уже привязан', 'ok'],
    rejected: ['Отклонён', 'bad'],
    conflict: ['Конфликт', 'bad'],
  };
  const KIND = { UK: 'Управляющая компания', REG_OPERATOR: 'Регоператор', OMSU: 'ОМСУ', DRT: 'ДРТ', UPRAVA: 'Управа', MPR: 'Минприроды', GZHI: 'ГЖИ' };
  const FRONT_ROLE = { INSPECTOR: 'ведёт дела', UK: 'сдаёт фотоотчёт по своим делам', ADMIN: 'только смотрит' };
  const AUDIT = {
    'auth.login': 'Вход',
    'engineer.created': 'Инженер добавлен', 'engineer.updated': 'Инженер изменён', 'engineer.max_unlinked': 'MAX отвязан от инженера',
    'territory.created': 'Участок добавлен', 'territory.updated': 'Участок изменён',
    'assignment.created': 'Назначение добавлено', 'assignment.updated': 'Назначение изменено',
    'executor.created': 'Исполнитель добавлен', 'executor.updated': 'Исполнитель изменён',
    'violation_type.created': 'Тип нарушения добавлен', 'violation_type.updated': 'Тип нарушения изменён',
    'registration.registered': 'Бот: инженер зарегистрирован', 'registration.pending_review': 'Бот: заявка на разбор',
    'registration.rejected': 'Регистрация отклонена', 'registration.resolved': 'Регистрация привязана вручную',
    'registration.conflict': 'Бот: конфликт регистрации', 'registration.already_registered': 'Бот: уже зарегистрирован',
    'role.created': 'Роль добавлена', 'role.updated': 'Роль изменена',
    'user.created': 'Пользователь добавлен', 'user.updated': 'Пользователь изменён',
    'integration.configured': 'Подключение DG настроено',
    'case.confirm': 'Дело подтверждено', 'case.dismiss': 'Дело отклонено', 'case.submit_report': 'Фотоотчёт сдан',
    'case.approve': 'Работа принята', 'case.return': 'Отчёт возвращён', 'case.escalate': 'Передано в КНМ', 'case.issue_act': 'Акт и предписание',
    'case.kp': 'Площадка дела уточнена',
    'engineer.deleted': 'Инженер удалён', 'territory.deleted': 'Участок удалён', 'assignment.deleted': 'Назначение удалено',
    'executor.deleted': 'Исполнитель удалён', 'violation_type.deleted': 'Тип нарушения удалён',
    'kp.created': 'Площадка заведена', 'kp.updated': 'Площадка изменена', 'kp.deleted': 'Площадка удалена', 'kp.restored': 'Площадка восстановлена',
    'kp.containers': 'Контейнеры площадки', 'kp.responsibles': 'Ответственные площадки', 'kp.imported': 'Загрузка из ФГИС УТКО',
  };
  const badge = (map, key) => {
    const [text, tone] = map[key] || [key || '—', ''];
    return `<span class="badge ${tone}">${esc(text)}</span>`;
  };
  const activeBadge = (on, off = 'Выключен') => (on ? '<span class="badge ok">Активен</span>' : `<span class="badge">${esc(off)}</span>`);

  // ── Разделы ─────────────────────────────────────────────────────────────
  const SECTIONS = [
    { id: 'overview', title: 'Обзор', sub: 'Состояние CRM, бота и интеграции с Data Gateway', perm: 'references.read' },
    { group: 'Работа' },
    { id: 'events', title: 'События DG', sub: 'Всё, что Data Gateway прислал в CRM', perm: 'events.read' },
    { id: 'cases', title: 'Дела', sub: 'Дела, созданные из событий, — только просмотр', perm: 'cases.read' },
    { id: 'registrations', title: 'Регистрации из бота', sub: 'Инженеры, которых CRM не нашла по телефону', perm: 'registrations.review' },
    { group: 'Справочники' },
    { id: 'engineers', title: 'Инженеры', sub: 'Инженеры ДРТ, их MAX и участки', perm: 'references.read' },
    { id: 'territories', title: 'Участки', sub: 'Территории, за которые отвечают инженеры', perm: 'references.read' },
    { id: 'assignments', title: 'Назначения', sub: 'Какой инженер на каком участке и с какого числа', perm: 'references.read' },
    { id: 'executors', title: 'Исполнители', sub: 'Ведомства и организации, которые устраняют нарушения', perm: 'references.read' },
    { id: 'types', title: 'Типы нарушений', sub: 'Справочник проблем из бота ДРТ', perm: 'references.read' },
    { id: 'kp', title: 'Площадки КП', sub: 'Реестр контейнерных площадок: ФГИС УТКО и проверки на месте', perm: 'references.read' },
    { group: 'Доступ' },
    { id: 'users', title: 'Пользователи', sub: 'Логины CRM и «Диспетчерской»', perm: 'users.manage' },
    { id: 'roles', title: 'Роли и права', sub: 'Что может каждая роль', perm: 'users.manage' },
    { id: 'audit', title: 'Журнал действий', sub: 'Кто, что и когда менял', perm: 'audit.read' },
    { group: 'Интеграция' },
    { id: 'dg', title: 'Data Gateway', sub: 'Подключение CRM к Data Gateway', perm: 'integration.manage' },
  ];

  const state = {
    me: null,
    perms: new Set(),
    cache: {},
    filters: { events: '', cases: '', registrations: 'pending_review', engineers: '', kp: '' },
    search: {},
    limits: { events: 50, cases: 100, kp: 50 },
    kpQuery: '',
    pending: 0,
  };
  const can = (perm) => state.perms.has(perm);
  const visibleSections = () => SECTIONS.filter((s) => s.id && can(s.perm));

  // ── API ────────────────────────────────────────────────────────────────
  class AuthError extends Error {}

  function errorText(data, status) {
    if (data && typeof data === 'object') {
      if (typeof data.message === 'string' && data.message) return data.message;
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
    }
    if (status === 403) return 'Недостаточно прав';
    return `Ошибка сервера (${status})`;
  }

  async function api(path, { method = 'GET', body } = {}) {
    let res;
    try {
      res = await fetch(API + path, {
        method,
        credentials: 'same-origin',
        headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new Error('Нет связи с CRM');
    }
    const text = await res.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch { data = text; }
    }
    if (res.status === 401 && path !== '/auth/login') {
      showLogin(state.me ? 'Сессия закончилась, войдите снова' : '');
      throw new AuthError('Нужен вход');
    }
    if (!res.ok) throw new Error(errorText(data, res.status));
    return data;
  }

  // Справочники нужны многим разделам — держим их до первой правки
  const REFS = {
    engineers: '/engineers',
    territories: '/territories',
    assignments: '/assignments',
    executors: '/executors',
    types: '/violation-types',
    roles: '/roles',
    permissions: '/permissions',
    users: '/users',
  };
  async function ref(key) {
    if (!state.cache[key]) state.cache[key] = api(REFS[key]);
    try {
      return await state.cache[key];
    } catch (err) {
      delete state.cache[key];
      throw err;
    }
  }
  const invalidate = (...keys) => keys.forEach((k) => delete state.cache[k]);
  const byId = (items, key) => Object.fromEntries(items.map((x) => [x[key], x]));

  // ── Каркас: вход, меню, отрисовка ──────────────────────────────────────
  const content = $('#content');
  let renderToken = 0;

  function showLogin(message) {
    state.me = null;
    state.perms = new Set();
    state.cache = {};
    if ($('#dialog').open) $('#dialog').close();
    $('#shell').hidden = true;
    $('#login').hidden = false;
    const err = $('#login-error');
    err.textContent = message || '';
    err.hidden = !message;
    $('#login-form [name=username]').focus();
  }

  function start(me) {
    state.me = me;
    state.perms = new Set(me.permissions || []);
    $('#login').hidden = true;
    $('#shell').hidden = false;
    const roleNames = (me.roles || []).join(', ');
    $('#me').innerHTML = `<strong>${esc(me.full_name || me.username)}</strong><small>${esc(me.username)}${roleNames ? ' · ' + esc(roleNames) : ''}</small>`;
    buildNav();
    refreshChrome();
    render();
  }

  function buildNav() {
    const visible = new Set(visibleSections().map((s) => s.id));
    const parts = [];
    let pendingGroup = null;
    for (const s of SECTIONS) {
      if (s.group) { pendingGroup = s.group; continue; }
      if (!visible.has(s.id)) continue;
      if (pendingGroup) { parts.push(`<p class="nav-group eyebrow">${esc(pendingGroup)}</p>`); pendingGroup = null; }
      const extra = s.id === 'registrations' ? '<span class="nav-badge" data-pending hidden></span>' : '';
      parts.push(`<a class="nav-item" href="#/${s.id}" data-nav="${s.id}"><span>${esc(s.title)}</span>${extra}</a>`);
    }
    $('#nav').innerHTML = parts.join('');
  }

  // Счётчик заявок из бота в меню и плашка DG внизу меню
  async function refreshChrome() {
    try {
      const s = await api('/admin/summary');
      paintChrome(s);
    } catch { /* обзор недоступен по правам — меню без счётчиков */ }
  }
  function paintChrome(s) {
    state.pending = s.registrations?.pending_review || 0;
    $$('[data-pending]').forEach((el) => { el.textContent = state.pending; el.hidden = !state.pending; });
    const chip = $('#dg-chip');
    if (!s.integration) { chip.hidden = true; return; }
    const i = s.integration;
    chip.hidden = false;
    chip.innerHTML = `<span class="dot ${i.configured ? 'ok' : 'bad'}"></span><div><strong>${i.configured ? 'DG подключён' : 'DG не подключён'}</strong>
      <small>${i.last_delivery_at ? 'последнее событие ' + fmt(i.last_delivery_at) : 'событий ещё не было'}</small></div>`;
  }

  function parseRoute() {
    const hash = location.hash.replace(/^#\/?/, '');
    const [view, ...rest] = hash.split('/');
    return { view, arg: rest.length ? decodeURIComponent(rest.join('/')) : null };
  }

  async function render() {
    if (!state.me) return;
    const sections = visibleSections();
    if (!sections.length) return renderNoAccess();
    const { view, arg } = parseRoute();
    const section = sections.find((s) => s.id === view);
    if (!section) { location.replace(`#/${sections[0].id}`); return; }
    $$('[data-nav]').forEach((a) => {
      if (a.dataset.nav === view) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    $('#page-title').textContent = section.title;
    $('#page-subtitle').textContent = section.sub;
    document.title = `${section.title} · Системный администратор · Чистый Липецк`;
    const token = ++renderToken;
    content.innerHTML = '<div class="loader">Загрузка…</div>';
    try {
      const html = await VIEWS[view](arg);
      if (token !== renderToken) return;
      content.innerHTML = html;
      applySearch();
    } catch (err) {
      if (err instanceof AuthError || token !== renderToken) return;
      content.innerHTML = `<div class="panel"><div class="empty">${esc(err.message)}</div></div>`;
    }
  }

  function renderNoAccess() {
    $('#nav').innerHTML = '';
    $('#page-title').textContent = 'Нет доступа к консоли';
    $('#page-subtitle').textContent = '';
    content.innerHTML = `<div class="panel"><div class="empty">У этой учётной записи нет прав администратора.<br>
      Рабочее место — <a href="/">«Диспетчерская»</a>.</div></div>`;
  }

  // Поиск по таблице: строки несут data-text, запрос живёт до следующего захода в раздел
  function applySearch() {
    $$('[data-search]', content).forEach((input) => {
      const q = state.search[input.dataset.search] || '';
      input.value = q;
      filterRows(input, q);
    });
  }
  function filterRows(input, q) {
    const needle = q.trim().toLowerCase();
    const scope = input.closest('.panel') || content;
    let shown = 0;
    $$('tbody tr[data-text]', scope).forEach((tr) => {
      const hit = !needle || tr.dataset.text.includes(needle);
      tr.hidden = !hit;
      if (hit) shown += 1;
    });
    const counter = $('[data-shown]', scope);
    if (counter) counter.textContent = needle ? `найдено: ${shown}` : '';
  }
  const rowText = (...parts) => esc(parts.filter((p) => p !== null && p !== undefined).join(' ').toLowerCase());

  // ── Кусочки разметки ───────────────────────────────────────────────────
  const panel = (head, body, { pad = false } = {}) => `<section class="panel">${head ? `<div class="panel-head">${head}</div>` : ''}${pad ? `<div class="panel-body">${body}</div>` : body}</section>`;
  const table = (headers, rows, emptyText = 'Записей нет') => `<div class="table-wrap"><table><thead><tr>${headers.map((h) => (typeof h === 'string' ? `<th>${h}</th>` : `<th class="${h.cls}">${h.t}</th>`)).join('')}</tr></thead><tbody>${rows.length ? rows.join('') : `<tr><td colspan="${headers.length}" class="empty">${esc(emptyText)}</td></tr>`}</tbody></table></div>`;
  const search = (key, placeholder = 'Поиск') => `<input class="search" type="search" data-search="${key}" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}"><span class="muted small" data-shown></span>`;
  const chips = (key, options) => `<div class="chips" role="group">${options.map(([value, label, n]) => `<button type="button" class="chip" data-action="filter" data-key="${key}" data-value="${esc(value)}" aria-pressed="${state.filters[key] === value}">${esc(label)}${n !== undefined ? `<span class="n">${n}</span>` : ''}</button>`).join('')}</div>`;
  const btn = (action, label, data = {}, cls = 'ghost small') => `<button type="button" class="btn ${cls}" data-action="${action}" ${Object.entries(data).map(([k, v]) => `data-${k}="${esc(v)}"`).join(' ')}>${esc(label)}</button>`;
  const kpi = (href, value, label, foot, tone = '') => `<a class="kpi" href="${href}"><span class="value ${tone}">${esc(value)}</span><span class="label">${esc(label)}</span>${foot ? `<span class="foot">${esc(foot)}</span>` : ''}</a>`;
  const facts = (pairs) => `<dl class="facts">${pairs.filter(Boolean).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;
  const maxId = (id) => (id ? `<span class="max-id">${esc(id)}</span>` : none('не привязан'));

  // ── Поля форм ──────────────────────────────────────────────────────────
  const field = (label, control, hint = '') => `<label class="field"><span>${esc(label)}</span>${control}${hint ? `<small class="hint">${esc(hint)}</small>` : ''}</label>`;
  const input = (name, label, value = '', { type = 'text', required = false, hint = '', attrs = '' } = {}) =>
    field(label, `<input name="${name}" type="${type}" value="${esc(value ?? '')}" ${required ? 'required' : ''} ${attrs}>`, hint);
  const textarea = (name, label, value = '', hint = '') => field(label, `<textarea name="${name}">${esc(value ?? '')}</textarea>`, hint);
  const select = (name, label, options, value, { required = false, empty = null, hint = '' } = {}) =>
    field(label, `<select name="${name}" ${required ? 'required' : ''}>${empty !== null ? `<option value="">${esc(empty)}</option>` : ''}${options.map(([v, t, disabled]) => `<option value="${esc(v)}" ${String(v) === String(value ?? '') ? 'selected' : ''} ${disabled ? 'disabled' : ''}>${esc(t)}</option>`).join('')}</select>`, hint);
  const check = (name, label, checked, value = 'on') => `<label class="check"><input type="checkbox" name="${name}" value="${esc(value)}" ${checked ? 'checked' : ''}><span>${label}</span></label>`;
  const str = (fd, name) => (fd.get(name) ?? '').toString().trim();
  const opt = (fd, name) => str(fd, name) || null;

  // ── Диалог ─────────────────────────────────────────────────────────────
  const dialog = $('#dialog');
  let dialogSubmit = null;

  function openDialog({ kicker = '', title, body, submit = 'Сохранить', danger = false, onSubmit }) {
    $('#dialog-kicker').textContent = kicker;
    $('#dialog-title').textContent = title;
    $('#dialog-body').innerHTML = body;
    const err = $('#dialog-error');
    err.hidden = true;
    const button = $('#dialog-submit');
    button.textContent = submit;
    button.className = `btn ${danger ? 'danger' : 'primary'}`;
    button.disabled = false;
    dialogSubmit = onSubmit;
    dialog.showModal();
    $('#dialog-body input:not([type=checkbox]):not([disabled]), #dialog-body select, #dialog-body textarea')?.focus();
  }

  $('#dialog-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!dialogSubmit) { dialog.close(); return; }
    const button = $('#dialog-submit');
    const err = $('#dialog-error');
    button.disabled = true;
    err.hidden = true;
    try {
      const message = await dialogSubmit(new FormData(event.target));
      dialog.close();
      if (message) toast(message);
      refreshChrome();
      render();
    } catch (e) {
      if (e instanceof AuthError) return;
      err.textContent = e.message;
      err.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
  dialog.addEventListener('click', (event) => {
    if (event.target.closest('[data-close]')) dialog.close();
  });

  let toastTimer = null;
  function toast(message, error = false) {
    const el = $('#toast');
    el.textContent = message;
    el.className = `toast show ${error ? 'error' : ''}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = 'toast'; }, 3200);
  }

  // ── Обзор ──────────────────────────────────────────────────────────────
  async function viewOverview() {
    const s = await api('/admin/summary');
    paintChrome(s);
    const e = s.engineers;
    const cards = [kpi('#/engineers', e.total, plural(e.total, 'инженер', 'инженера', 'инженеров'), `с MAX — ${e.with_max}, без MAX — ${e.total - e.with_max}`)];
    if (s.registrations) {
      const p = s.registrations.pending_review || 0;
      cards.push(kpi('#/registrations', p, plural(p, 'заявка из бота ждёт разбора', 'заявки из бота ждут разбора', 'заявок из бота ждут разбора'), 'телефон не нашёлся в CRM', p ? 'alert' : ''));
    }
    if (s.events) {
      const total = sum(s.events);
      cards.push(kpi('#/events', total, plural(total, 'событие от DG', 'события от DG', 'событий от DG'), `с расхождениями — ${s.events.NEEDS_REVIEW || 0}, ошибок — ${s.events.FAILED || 0}`, s.events.FAILED ? 'bad' : ''));
    }
    if (s.cases) {
      const open = (s.cases.NEW || 0) + (s.cases.IN_PROGRESS || 0) + (s.cases.VERIFICATION || 0) + (s.cases.KNM_ESCALATION || 0);
      cards.push(kpi('#/cases', open, plural(open, 'дело не закрыто', 'дела не закрыты', 'дел не закрыто'), `просрочено — ${s.cases.overdue || 0}`, s.cases.overdue ? 'alert' : ''));
    }

    let casesPanel = '';
    if (s.cases) {
      const statuses = Object.keys(CASE_STATUS);
      const total = statuses.reduce((a, k) => a + (s.cases[k] || 0), 0);
      const bar = total ? statuses.filter((k) => s.cases[k]).map((k) => `<span style="width:${(100 * s.cases[k]) / total}%;background:${CASE_COLORS[k]}" title="${esc(CASE_STATUS[k][0])}"></span>`).join('') : '';
      casesPanel = panel(`<h2>Дела по статусам</h2><span class="muted small">всего ${total}</span>`,
        `<div class="statusbar">${bar}</div><div class="legend">${statuses.map((k) => `<div><span><i style="background:${CASE_COLORS[k]}"></i>${esc(CASE_STATUS[k][0])}</span><b>${s.cases[k] || 0}</b></div>`).join('')}</div>`, { pad: true });
    }

    const refs = facts([
      ['Участки', `${s.territories} <a href="#/territories">открыть</a>`],
      ['Назначения', `${s.assignments} <a href="#/assignments">открыть</a>`],
      ['Исполнители', `${s.executors} <a href="#/executors">открыть</a>`],
      ['Типы нарушений', `${s.violation_types} <a href="#/types">открыть</a>`],
      s.kp && ['Площадки КП', `${s.kp.total}${s.kp.review ? `, на проверку ${s.kp.review}` : ''} <a href="#/kp">открыть</a>`],
      s.users && ['Пользователи', `${s.users.active} активных из ${s.users.total} <a href="#/users">открыть</a>`],
    ]);
    const dg = s.integration ? panel('<h2>Data Gateway</h2><a href="#/dg">подробнее</a>', dgFacts(s.integration), { pad: true }) : '';

    return `<div class="kpis">${cards.join('')}</div>
      <div class="split"><div style="display:grid;gap:16px">${casesPanel}${panel('<h2>Справочники и доступ</h2><span class="muted small">только активные записи</span>', refs, { pad: true })}</div>${dg}</div>`;
  }

  function dgFacts(i) {
    return facts([
      ['Состояние', i.configured ? '<span class="badge ok">Подключён</span>' : '<span class="badge bad">Не подключён</span>'],
      ['Потребитель', i.consumer_key ? `<code>${esc(i.consumer_key)}</code>` : '—'],
      ['Адрес DG', i.datagateway_url ? `<code>${esc(i.datagateway_url)}</code>` : '—'],
      ['Подключён', fmt(i.configured_at)],
      ['Последнее событие', fmt(i.last_delivery_at)],
      ['Приём событий', `<code>POST ${esc(i.webhook_path)}</code>`],
    ]);
  }

  // ── События DG ─────────────────────────────────────────────────────────
  async function viewEvents(arg) {
    if (arg) return viewEvent(arg);
    const status = state.filters.events;
    const [page, summary] = await Promise.all([
      api(`/events?limit=${state.limits.events}${status ? `&status=${encodeURIComponent(status)}` : ''}`),
      api('/admin/summary').catch(() => null),
    ]);
    const counts = summary?.events || {};
    const options = [['', 'Все', sum(counts)], ...Object.keys(EVENT_STATUS).map((k) => [k, EVENT_STATUS[k][0], counts[k] || 0])];
    const rows = page.items.map((e) => `<tr class="clickable" data-href="#/events/${encodeURIComponent(e.event_id)}" data-text="${rowText(e.event_id, e.source, e.source_event_id, e.status, e.error)}">
      <td>${fmt(e.received_at)}<span class="sub">разобрано ${fmt(e.processed_at)}</span></td>
      <td><code class="wrap-anywhere">${esc(e.event_id)}</code></td>
      <td>${esc(e.source)}<span class="sub mono wrap-anywhere">${esc(e.source_event_id || '')}</span></td>
      <td><code>${esc(e.schema)}</code></td>
      <td>${badge(EVENT_STATUS, e.status)}${e.error ? `<span class="sub wrap-anywhere">${esc(e.error.slice(0, 160))}</span>` : ''}</td>
      <td class="num">${e.duplicate_count || 0}</td></tr>`);
    const more = page.total > page.items.length && state.limits.events < 500
      ? `<div class="panel-body" style="text-align:center">${btn('more', `Показать ещё (${page.items.length} из ${page.total})`, { key: 'events' }, 'ghost')}</div>` : '';
    return `<div class="toolbar">${chips('events', options)}</div>` +
      panel(`<div class="toolbar left">${search('events', 'ID события, источник, ошибка')}</div><span class="muted small">показано ${page.items.length} из ${page.total}</span>`,
        table(['Получено', 'Событие', 'Источник', 'Схема', 'Статус', { t: 'Повторы', cls: 'num' }], rows, 'Событий нет') + more);
  }

  function flatten(value, prefix = '', out = []) {
    if (Array.isArray(value)) {
      if (!value.length) out.push([prefix, '[]']);
      value.forEach((item, i) => flatten(item, `${prefix}[${i}]`, out));
    } else if (value && typeof value === 'object') {
      const entries = Object.entries(value);
      if (!entries.length) out.push([prefix, '{}']);
      entries.forEach(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k, out));
    } else {
      out.push([prefix, value]);
    }
    return out;
  }
  const scalar = (v) => (v === null || v === undefined || v === '' ? none('пусто') : typeof v === 'boolean' ? (v ? 'да' : 'нет') : esc(v));

  async function viewEvent(id) {
    const [ev, cases] = await Promise.all([
      api(`/events/${encodeURIComponent(id)}`),
      can('cases.read') ? api(`/cases?event_id=${encodeURIComponent(id)}`) : Promise.resolve({ items: [] }),
    ]);
    const c = ev.canonical || {};
    const rep = c.reporter || {};
    const vio = c.violation || {};
    const loc = c.location || {};
    const addr = loc.address || {};
    const coords = loc.coordinates || {};
    const media = Array.isArray(c.media) ? c.media : [];
    // Проблема на КП от жителей (Домовой ГЖИ): вместо инженера и нарушения — источник и проблема
    const prob = c.event_type === 'waste_site_problem' ? (c.problem || {}) : null;
    const title = prob ? (prob.theme?.short_name || prob.theme?.name || 'Проблема на КП') : vio.type?.name;
    $('#page-title').textContent = title || 'Событие';
    $('#page-subtitle').textContent = `Событие ${ev.event_id}`;

    const engineerLink = rep.engineer_id
      ? `<a href="#/engineers" data-action="goto" data-view="engineers" data-q="${esc(rep.engineer_id)}">${esc(rep.engineer_id)}</a>` : '—';
    const caseBlock = cases.items.length
      ? cases.items.map((x) => facts([
        ['Дело', `№ ${esc(x.id)}`],
        ['Статус', badge(CASE_STATUS, x.status)],
        ['Срок', fmt(x.deadline_at)],
        x.review_reason && ['Расхождение', esc(x.review_reason)],
        x.kp_id && ['Площадка КП', `<a href="#/kp/${encodeURIComponent(x.kp_id)}">открыть карточку</a><span class="sub">${esc(x.kp_method || '')}${x.kp_score != null ? ` · уверенность ${esc(x.kp_score)}` : ''}</span>`],
      ])).join('')
      : `<p class="muted">${ev.status === 'RECEIVED' ? 'Событие ещё не разобрано.' : 'Дело по событию не создано.'}</p>`;

    const mediaBlock = media.length
      ? `<ul class="media-list">${media.map((m, i) => {
        const url = `${API}/events/${encodeURIComponent(ev.event_id)}/media/${i}`;
        const size = m.size_bytes ? `${Math.round(m.size_bytes / 1024)} КБ` : '';
        const thumb = m.type === 'image' ? `<a href="${url}" target="_blank" rel="noopener"><img class="thumb" src="${url}" alt="Снимок ${i + 1}"></a>` : '';
        return `<li>${thumb}${esc(m.type || 'файл')} ${i + 1} · <span class="muted">${esc([m.content_type, size].filter(Boolean).join(', '))}</span>
          · <a href="${url}" target="_blank" rel="noopener">открыть</a>
          <span class="sub mono wrap-anywhere">${esc(m.storage?.key || '')}</span></li>`;
      }).join('')}</ul><p class="muted small" style="margin-top:8px">Файлы отдаёт CRM по постоянной ссылке: снимки она забирает к себе при приёме, видео берёт из хранилища DG по свежей ссылке.</p>`
      : '<p class="muted">Файлов нет.</p>';

    const groups = {};
    flatten(c).forEach(([path, v]) => {
      const top = path.split(/[.[]/)[0] || 'прочее';
      (groups[top] = groups[top] || []).push([path, v]);
    });
    const site = c.waste_site || {};
    const hint = (prob?.responsible_hint?.organizations || []).map((o) => o.name).join(', ');
    const counts = prob ? [['домов', prob.houses_count], ['сообщений', prob.messages_count], ['жителей', prob.residents_count]]
      .filter(([, n]) => n !== null && n !== undefined).map(([label, n]) => `${label}: ${n}`).join(', ') : '';
    const whoPanels = prob
      ? panel('<h2>Источник</h2>', facts([['Система', esc(c.source?.system || c.source?.type || '—')], ['Канал', esc(c.source?.channel || '—')], ['Проблема', `<code class="wrap-anywhere">${esc(c.source?.problem_id || '—')}</code>`], ['Ревизия', esc(c.source?.revision ?? '—')]]), { pad: true })
        + panel('<h2>Проблема</h2>', facts([['Тема', `${esc(prob.theme?.name || '—')}<span class="sub mono">${esc(prob.theme?.eds_code || '')}</span>`], ['Описание', esc(prob.summary || '—')], ['Чаты', esc(counts || '—')], ['Ответственный', hint ? `${esc(hint)}<span class="sub">подсказка источника</span>` : '—'], ['Площадка', site.utko_id ? `${esc(site.address || '—')}<span class="sub mono">УТКО ${esc(site.utko_id)}${site.code ? ` · у источника ${esc(site.code)}` : ''}</span>` : '—']]), { pad: true })
      : panel('<h2>Инженер</h2>', facts([['ФИО', esc(rep.name || '—')], ['ID в CRM', engineerLink], ['Назначение', esc(c.assignment?.id || '—')], ['Участок', esc(c.assignment?.territory_id || '—')]]), { pad: true })
        + panel('<h2>Нарушение</h2>', facts([['Тип', `${esc(vio.type?.name || '—')}<span class="sub mono">${esc(vio.type?.type_violation_id || '')}</span>`], ['Исполнитель', `${esc(vio.executor?.name || '—')}<span class="sub mono">${esc(vio.executor?.executor_id || '')}</span>`], ['Комментарий', esc(vio.comment || '—')]]), { pad: true });
    const address = typeof loc.address === 'string' ? loc.address : (addr.formatted || [addr.city, addr.street, addr.house].filter(Boolean).join(', '));

    const tree = Object.entries(groups).map(([top, rows]) => `<div class="tree-section"><h3>${esc(top)}</h3><div class="tree">${rows.map(([p, v]) => `<div class="tree-row"><code>${esc(p)}</code><span class="v">${scalar(v)}</span></div>`).join('')}</div></div>`).join('');

    return `<a class="btn ghost small back" href="#/events">← Все события</a>
      <div class="detail-hero"><div><span class="eyebrow">${esc(c.event_type || 'событие')} · ${esc(ev.schema)}</span><h2>${esc(title || 'Событие без типа')}</h2><code class="muted wrap-anywhere">${esc(ev.event_id)}</code></div>
        <div>${badge(EVENT_STATUS, ev.status)}</div></div>
      ${ev.error ? `<p class="form-error ${ev.status === 'NEEDS_REVIEW' ? 'warn' : ''}">${ev.status === 'NEEDS_REVIEW' ? 'Расхождение со справочниками: ' : ''}${esc(ev.error)}</p>` : ''}
      <div class="cards-3">
        ${whoPanels}
        ${panel('<h2>Место</h2>', facts([['Адрес', esc(address || '—')], ['Координаты', coords.latitude !== undefined ? `<span class="mono">${esc(coords.latitude)}, ${esc(coords.longitude)}</span>` : '—'], ['Точность', loc.accuracy_meters !== undefined && loc.accuracy_meters !== null ? `${esc(loc.accuracy_meters)} м` : '—']]), { pad: true })}
        ${panel('<h2>Дело в CRM</h2>', caseBlock, { pad: true })}
        ${panel('<h2>Доставка</h2>', facts([['Получено', fmt(ev.received_at)], ['Разобрано', fmt(ev.processed_at)], ['Источник', esc(ev.source)], ['ID в источнике', `<code>${esc(ev.source_event_id || '—')}</code>`], ['Повторов', esc(ev.duplicate_count || 0)], ['SHA-256', `<code class="wrap-anywhere">${esc(ev.payload_sha256 || '—')}</code>`]]), { pad: true })}
        ${panel(`<h2>Файлы</h2><span class="muted small">${media.length}</span>`, mediaBlock, { pad: true })}
      </div>
      ${panel('<h2>Все поля события</h2><span class="muted small">каноническая модель DG</span>', tree || '<p class="muted">Пусто</p>', { pad: true })}
      <details class="raw"><summary>Исходный JSON события</summary><pre>${esc(JSON.stringify(c, null, 2))}</pre></details>
      <details class="raw"><summary>Конверт доставки</summary><pre>${esc(JSON.stringify(ev.envelope, null, 2))}</pre></details>`;
  }

  // ── Дела ───────────────────────────────────────────────────────────────
  async function viewCases() {
    const status = state.filters.cases;
    const [page, executors, types, summary] = await Promise.all([
      api(`/cases?limit=${state.limits.cases}${status ? `&status=${encodeURIComponent(status)}` : ''}`),
      can('references.read') ? ref('executors') : Promise.resolve([]),
      can('references.read') ? ref('types') : Promise.resolve([]),
      api('/admin/summary').catch(() => null),
    ]);
    const ex = byId(executors, 'executor_id');
    const ty = byId(types, 'type_violation_id');
    const counts = summary?.cases || {};
    const options = [['', 'Все', Object.keys(CASE_STATUS).reduce((a, k) => a + (counts[k] || 0), 0)], ...Object.keys(CASE_STATUS).map((k) => [k, CASE_STATUS[k][0], counts[k] || 0])];
    const now = Date.now();
    const rows = page.items.map((c) => {
      const overdue = c.status === 'IN_PROGRESS' && c.deadline_at && new Date(c.deadline_at).getTime() < now;
      const typeName = ty[c.type_violation_id]?.name;
      const exName = ex[c.executor_id]?.name;
      return `<tr data-text="${rowText(c.id, typeName, exName, c.address, c.engineer_id, c.status)}">
        <td class="num">${esc(c.id)}</td>
        <td>${badge(CASE_STATUS, c.status)}${c.review_reason ? '<span class="sub" style="color:var(--warning)">есть расхождение</span>' : ''}</td>
        <td>${esc(typeName || '—')}<span class="sub mono">${esc(c.type_violation_id || '')}</span></td>
        <td>${esc(exName || '—')}</td>
        <td class="wrap-anywhere">${esc(c.address || '—')}</td>
        <td>${fmt(c.created_at)}</td>
        <td${overdue ? ' style="color:var(--danger)"' : ''}>${fmt(c.deadline_at)}${overdue ? '<span class="sub">просрочено</span>' : ''}</td>
        <td>${c.event_id ? `<a href="#/events/${encodeURIComponent(c.event_id)}">событие</a>` : '—'}</td></tr>`;
    });
    return `<div class="toolbar">${chips('cases', options)}<a class="btn ghost small" href="/" target="_blank" rel="noopener">Вести дела — в «Диспетчерской» ↗</a></div>` +
      panel(`<div class="toolbar left">${search('cases', 'Номер, тип, исполнитель, адрес')}</div><span class="muted small">показано ${page.items.length} из ${page.total}</span>`,
        table([{ t: '№', cls: 'num' }, 'Статус', 'Тип нарушения', 'Исполнитель', 'Адрес', 'Создано', 'Срок', ''], rows, 'Дел нет'));
  }

  // ── Регистрации из бота ────────────────────────────────────────────────
  async function viewRegistrations() {
    const status = state.filters.registrations;
    const [items, engineers] = await Promise.all([
      api(`/registrations${status ? `?status=${encodeURIComponent(status)}` : ''}`),
      can('references.read') ? ref('engineers') : Promise.resolve([]),
    ]);
    const eng = byId(engineers, 'engineer_id');
    const rows = items.map((r) => {
      const who = r.engineer_id ? `<a href="#/engineers" data-action="goto" data-view="engineers" data-q="${esc(r.engineer_id)}">${esc(eng[r.engineer_id]?.full_name || r.engineer_id)}</a>` : '';
      const actions = r.status === 'pending_review'
        ? btn('reg-resolve', 'Привязать к инженеру', { id: r.registration_id }, 'primary small') + btn('reg-reject', 'Отклонить', { id: r.registration_id }, 'danger small') : '';
      return `<tr data-text="${rowText(r.max_user_id, r.phone, r.status, r.engineer_id, eng[r.engineer_id]?.full_name, r.reason)}">
        <td>${fmt(r.requested_at || r.created_at)}</td>
        <td>${maxId(r.max_user_id)}</td>
        <td class="mono">${esc(r.phone || '—')}</td>
        <td>${badge(REG_STATUS, r.status)}</td>
        <td>${who || esc(r.reason || '—')}</td>
        <td>${r.resolved_by ? `${esc(r.resolved_by)}<span class="sub">${fmt(r.resolved_at)}</span>` : '—'}</td>
        <td class="actions">${actions}</td></tr>`;
    });
    const options = [['pending_review', 'На разборе', state.pending], ['registered', 'Привязаны'], ['rejected', 'Отклонены'], ['', 'Все']];
    return `<div class="toolbar">${chips('registrations', options)}</div>
      <p class="muted small">Бот присылает телефон инженера. Нашёлся в CRM — MAX привязывается сам. Не нашёлся — заявка ждёт здесь: привяжите её к инженеру из справочника или отклоните.</p>` +
      panel(`<div class="toolbar left">${search('registrations', 'MAX ID, телефон, инженер')}</div>`,
        table(['Запрос', 'MAX user ID', 'Телефон', 'Статус', 'Инженер или причина', 'Разобрал', ''], rows, status === 'pending_review' ? 'Заявок на разборе нет' : 'Заявок нет'));
  }

  async function resolveRegistration(id) {
    const [regs, engineers] = await Promise.all([api('/registrations?status=pending_review'), ref('engineers')]);
    const reg = regs.find((r) => r.registration_id === id);
    if (!reg) throw new Error('Заявка уже разобрана');
    const options = engineers.filter((e) => e.is_active).map((e) => [e.engineer_id, `${e.full_name} · ${e.phone}${e.max_user_id ? ' · уже с MAX' : ''}`, Boolean(e.max_user_id)]);
    openDialog({
      kicker: 'Заявка из бота',
      title: 'Привязать MAX к инженеру',
      body: facts([['MAX user ID', maxId(reg.max_user_id)], ['Телефон из бота', `<span class="mono">${esc(reg.phone)}</span>`]]) +
        select('engineer_id', 'Инженер', options, '', { required: true, empty: '— выберите —', hint: 'Инженеры, у которых MAX уже привязан, недоступны. Если телефон в CRM устарел — поправьте его в карточке инженера.' }),
      submit: 'Привязать',
      onSubmit: async (fd) => {
        await api(`/registrations/${encodeURIComponent(id)}/resolve`, { method: 'POST', body: { engineer_id: str(fd, 'engineer_id') } });
        invalidate('engineers');
        return 'MAX привязан — бот узнает инженера';
      },
    });
  }

  function rejectRegistration(id) {
    openDialog({
      kicker: 'Заявка из бота',
      title: 'Отклонить регистрацию',
      body: textarea('reason', 'Причина', '', 'Видна в журнале и в списке заявок.'),
      submit: 'Отклонить',
      danger: true,
      onSubmit: async (fd) => {
        const reason = str(fd, 'reason');
        if (reason.length < 3) throw new Error('Напишите причину');
        await api(`/registrations/${encodeURIComponent(id)}/reject`, { method: 'POST', body: { reason } });
        return 'Регистрация отклонена';
      },
    });
  }

  // ── Инженеры ───────────────────────────────────────────────────────────
  async function viewEngineers() {
    const engineers = await ref('engineers');
    const write = can('engineers.write');
    const f = state.filters.engineers;
    const withMax = engineers.filter((e) => e.max_user_id).length;
    const list = engineers.filter((e) => (f === 'max' ? e.max_user_id : f === 'nomax' ? !e.max_user_id : f === 'off' ? !e.is_active : true));
    const rows = list.map((e) => {
      const a = e.current_assignment;
      const actions = write
        ? btn('engineer-edit', 'Изменить', { id: e.engineer_id }) + btn('engineer-assign', 'На участок', { id: e.engineer_id }) +
          (e.max_user_id ? btn('engineer-unlink', 'Отвязать MAX', { id: e.engineer_id }, 'danger small') : '') +
          btn('ref-delete', 'Удалить', { kind: 'engineers', id: e.engineer_id, name: e.full_name }, 'danger small') : '';
      return `<tr data-text="${rowText(e.engineer_id, e.full_name, e.phone, e.email, e.max_user_id, a?.territory_name)}">
        <td><strong>${esc(e.full_name)}</strong><span class="sub mono">${esc(e.engineer_id)}</span></td>
        <td class="mono">${esc(e.phone || '—')}</td>
        <td>${esc(e.email || '—')}</td>
        <td>${maxId(e.max_user_id)}</td>
        <td>${a ? `${esc(a.territory_name)}<span class="sub">${a.route_id ? 'маршрут ' + esc(a.route_id) + ' · ' : ''}с ${fmtDay(a.starts_on)}</span>` : none('не назначен')}</td>
        <td>${activeBadge(e.is_active)}</td>
        <td class="actions">${actions}</td></tr>`;
    });
    const options = [['', 'Все', engineers.length], ['max', 'С MAX', withMax], ['nomax', 'Без MAX', engineers.length - withMax], ['off', 'Выключены', engineers.filter((e) => !e.is_active).length]];
    return `<div class="toolbar">${chips('engineers', options)}${write ? btn('engineer-new', '+ Инженер', {}, 'primary') : ''}</div>
      <p class="muted small">MAX user ID указывают при создании инженера — или он появляется сам, когда инженер регистрируется в боте ДРТ по телефону. По нему Data Gateway узнаёт, кто прислал нарушение.</p>` +
      panel(`<div class="toolbar left">${search('engineers', 'ФИО, телефон, MAX ID, участок')}</div>`,
        table(['Инженер', 'Телефон', 'Email', 'MAX user ID', 'Участок сейчас', 'Статус', ''], rows, 'Инженеров нет'));
  }

  async function editEngineer(id) {
    const e = id ? (await ref('engineers')).find((x) => x.engineer_id === id) : null;
    openDialog({
      kicker: e ? e.engineer_id : 'Новый инженер',
      title: e ? e.full_name : 'Инженер ДРТ',
      body: input('full_name', 'ФИО', e?.full_name, { required: true, attrs: 'minlength="3"' }) +
        `<div class="grid-2">${input('phone', 'Телефон', e?.phone, { required: true, type: 'tel', hint: 'По нему бот находит инженера. Любой формат: +7, 8, со скобками.' })}${input('email', 'Email', e?.email, { type: 'email' })}</div>` +
        input('max_user_id', 'MAX user ID', e?.max_user_id, { attrs: 'maxlength="128" autocomplete="off" spellcheck="false"', hint: 'Указан — бот узнаёт инженера сразу, без регистрации по телефону. Пусто — инженер зарегистрируется в боте сам.' }) +
        check('is_active', 'Активен — бот и Data Gateway принимают его сообщения', e ? e.is_active : true),
      onSubmit: async (fd) => {
        const body = { full_name: str(fd, 'full_name'), phone: str(fd, 'phone'), email: opt(fd, 'email'), max_user_id: opt(fd, 'max_user_id'), is_active: fd.get('is_active') === 'on' };
        await api(e ? `/engineers/${encodeURIComponent(id)}` : '/engineers', { method: e ? 'PATCH' : 'POST', body });
        invalidate('engineers');
        return e ? 'Инженер сохранён' : 'Инженер добавлен';
      },
    });
  }

  async function unlinkMax(id) {
    const e = (await ref('engineers')).find((x) => x.engineer_id === id);
    openDialog({
      kicker: e.engineer_id,
      title: 'Отвязать MAX',
      body: `<p>Отвязать MAX ${maxId(e.max_user_id)} от инженера <strong>${esc(e.full_name)}</strong>?</p>
        <p class="muted">Бот перестанет его узнавать и попросит зарегистрироваться заново по телефону. Нужно, если инженер сменил телефон или аккаунт MAX.</p>`,
      submit: 'Отвязать',
      danger: true,
      onSubmit: async () => {
        await api(`/engineers/${encodeURIComponent(id)}/unlink-max`, { method: 'POST' });
        invalidate('engineers');
        return 'MAX отвязан';
      },
    });
  }

  // ── Участки и назначения ───────────────────────────────────────────────
  const boundsText = (b) => (b ? `<span class="mono small">${esc(b.south)}–${esc(b.north)} с. ш.<br>${esc(b.west)}–${esc(b.east)} в. д.</span>` : none('не заданы'));

  async function viewTerritories() {
    const [territories, assignments] = await Promise.all([ref('territories'), ref('assignments')]);
    const write = can('references.write');
    const count = {};
    assignments.filter((a) => a.is_active).forEach((a) => { count[a.territory_id] = (count[a.territory_id] || 0) + 1; });
    const rows = territories.map((t) => `<tr data-text="${rowText(t.territory_id, t.name)}">
      <td><strong>${esc(t.name)}</strong><span class="sub mono">${esc(t.territory_id)}</span></td>
      <td>${boundsText(t.bounds)}</td>
      <td class="num">${count[t.territory_id] || 0}</td>
      <td>${activeBadge(t.is_active)}</td>
      <td class="actions">${write ? btn('territory-edit', 'Изменить', { id: t.territory_id }) + btn('ref-delete', 'Удалить', { kind: 'territories', id: t.territory_id, name: t.name }, 'danger small') : ''}</td></tr>`);
    return `<div class="toolbar"><p class="muted small">Границы — прямоугольник: по ним DG проверяет, что нарушение снято на участке инженера.</p>${write ? btn('territory-new', '+ Участок', {}, 'primary') : ''}</div>` +
      panel(`<div class="toolbar left">${search('territories', 'Название или ID')}</div>`,
        table(['Участок', 'Границы', { t: 'Инженеров', cls: 'num' }, 'Статус', ''], rows, 'Участков нет'));
  }

  async function editTerritory(id) {
    const t = id ? (await ref('territories')).find((x) => x.territory_id === id) : null;
    const b = t?.bounds || {};
    const num = (name, label) => input(name, label, b[name], { type: 'number', attrs: 'step="any"' });
    openDialog({
      kicker: t ? t.territory_id : 'Новый участок',
      title: t ? t.name : 'Участок',
      body: input('name', 'Название', t?.name, { required: true, attrs: 'minlength="2"' }) +
        `<div class="grid-4">${num('south', 'Юг, широта')}${num('north', 'Север, широта')}${num('west', 'Запад, долгота')}${num('east', 'Восток, долгота')}</div>
        <small class="hint muted">Все четыре или ни одной. Пусто — DG не проверяет попадание в участок.</small>` +
        check('is_active', 'Активен', t ? t.is_active : true),
      onSubmit: async (fd) => {
        const keys = ['south', 'north', 'west', 'east'];
        const filled = keys.filter((k) => str(fd, k) !== '');
        if (filled.length && filled.length < 4) throw new Error('Заполните все четыре границы или оставьте их пустыми');
        const bounds = filled.length ? Object.fromEntries(keys.map((k) => [k, Number(str(fd, k))])) : null;
        if (bounds && (bounds.south >= bounds.north || bounds.west >= bounds.east)) throw new Error('Юг должен быть меньше севера, запад — меньше востока');
        await api(t ? `/territories/${encodeURIComponent(id)}` : '/territories', { method: t ? 'PATCH' : 'POST', body: { name: str(fd, 'name'), bounds, is_active: fd.get('is_active') === 'on' } });
        invalidate('territories', 'engineers');
        return t ? 'Участок сохранён' : 'Участок добавлен';
      },
    });
  }

  async function viewAssignments() {
    const [assignments, engineers] = await Promise.all([ref('assignments'), ref('engineers')]);
    const eng = byId(engineers, 'engineer_id');
    const write = can('engineers.write');
    const rows = assignments.map((a) => `<tr data-text="${rowText(a.assignment_id, a.engineer_id, eng[a.engineer_id]?.full_name, a.territory_name, a.route_id)}">
      <td class="mono">${esc(a.assignment_id)}</td>
      <td>${esc(eng[a.engineer_id]?.full_name || a.engineer_id)}<span class="sub mono">${esc(a.engineer_id)}</span></td>
      <td>${esc(a.territory_name)}<span class="sub mono">${esc(a.territory_id)}</span></td>
      <td>${esc(a.route_id || '—')}</td>
      <td>${fmtDay(a.starts_on)} — ${a.ends_on ? fmtDay(a.ends_on) : 'бессрочно'}</td>
      <td>${activeBadge(a.is_active, 'Снято')}</td>
      <td class="actions">${write ? btn('assignment-edit', 'Изменить', { id: a.assignment_id }) + btn('ref-delete', 'Удалить', { kind: 'assignments', id: a.assignment_id, name: `${eng[a.engineer_id]?.full_name || a.engineer_id} — ${a.territory_name}` }, 'danger small') : ''}</td></tr>`);
    return `<div class="toolbar"><p class="muted small">Текущим считается действующее назначение с самой поздней датой начала.</p>${write ? btn('assignment-new', '+ Назначение', {}, 'primary') : ''}</div>` +
      panel(`<div class="toolbar left">${search('assignments', 'Инженер, участок, маршрут')}</div>`,
        table(['ID', 'Инженер', 'Участок', 'Маршрут', 'Период', 'Статус', ''], rows, 'Назначений нет'));
  }

  async function editAssignment(id, engineerId = null) {
    const [assignments, engineers, territories] = await Promise.all([ref('assignments'), ref('engineers'), ref('territories')]);
    const a = id ? assignments.find((x) => x.assignment_id === id) : null;
    const eng = byId(engineers, 'engineer_id');
    const terr = territories.filter((t) => t.is_active || t.territory_id === a?.territory_id).map((t) => [t.territory_id, t.name]);
    const engineerField = a
      ? field('Инженер', `<div>${esc(eng[a.engineer_id]?.full_name || a.engineer_id)}</div>`)
      : select('engineer_id', 'Инженер', engineers.filter((e) => e.is_active).map((e) => [e.engineer_id, e.full_name]), engineerId, { required: true, empty: '— выберите —' });
    openDialog({
      kicker: a ? a.assignment_id : 'Новое назначение',
      title: a ? 'Назначение' : engineerId ? `${eng[engineerId]?.full_name} — на участок` : 'Назначить инженера на участок',
      body: engineerField + select('territory_id', 'Участок', terr, a?.territory_id, { required: true, empty: '— выберите —' }) +
        input('route_id', 'Маршрут', a?.route_id, { hint: 'Необязательно' }) +
        `<div class="grid-2">${input('starts_on', 'С', a ? a.starts_on : today(), { type: 'date' })}${input('ends_on', 'По', a?.ends_on, { type: 'date', hint: 'Пусто — бессрочно' })}</div>` +
        check('is_active', 'Действует', a ? a.is_active : true),
      onSubmit: async (fd) => {
        const body = { territory_id: str(fd, 'territory_id'), route_id: opt(fd, 'route_id'), starts_on: opt(fd, 'starts_on'), ends_on: opt(fd, 'ends_on'), is_active: fd.get('is_active') === 'on' };
        if (body.starts_on && body.ends_on && body.ends_on < body.starts_on) throw new Error('Дата окончания раньше начала');
        if (a) await api(`/assignments/${encodeURIComponent(id)}`, { method: 'PATCH', body });
        else await api('/assignments', { method: 'POST', body: { engineer_id: str(fd, 'engineer_id'), ...body } });
        invalidate('assignments', 'engineers');
        return a ? 'Назначение сохранено' : 'Инженер назначен';
      },
    });
  }

  // ── Исполнители и типы ─────────────────────────────────────────────────
  async function viewExecutors() {
    const executors = await ref('executors');
    const write = can('references.write');
    const rows = executors.map((x) => {
      const tags = x.violation_types.slice(0, 3).map((v) => `<span class="tag">${esc(v.name)}</span>`).join('');
      const more = x.violation_types.length > 3 ? `<span class="muted small">и ещё ${x.violation_types.length - 3}</span>` : '';
      return `<tr data-text="${rowText(x.executor_id, x.code, x.name, x.full_name, KIND[x.kind], ...x.violation_types.map((v) => v.name))}">
        <td><strong>${esc(x.name)}</strong><span class="sub">${esc(x.full_name || '')}</span></td>
        <td class="mono small">${esc(x.code || '—')}<span class="sub">${esc(x.executor_id)}</span></td>
        <td>${esc(KIND[x.kind] || x.kind)}</td>
        <td><span class="mono">${x.violation_types.length}</span> ${tags}${more}</td>
        <td>${activeBadge(x.is_active)}</td>
        <td class="actions">${write ? btn('executor-edit', 'Изменить', { id: x.executor_id }) + btn('ref-delete', 'Удалить', { kind: 'executors', id: x.executor_id, name: x.name }, 'danger small') : ''}</td></tr>`;
    });
    return `<div class="toolbar"><p class="muted small">Ключ ведомства (code) — тот же, что в боте ДРТ; это и логин аккаунта ведомства.</p>${write ? btn('executor-new', '+ Исполнитель', {}, 'primary') : ''}</div>` +
      panel(`<div class="toolbar left">${search('executors', 'Название, ключ, тип нарушения')}</div>`,
        table(['Организация', 'Ключ / ID', 'Вид', 'Устраняет', 'Статус', ''], rows, 'Исполнителей нет'));
  }

  function typeChecks(types, executors, selected) {
    const owner = {};
    executors.forEach((x) => { if (x.code) owner[x.code] = x.name; });
    const groups = {};
    types.forEach((t) => {
      const key = (t.code || '').split('.')[0] || 'прочее';
      (groups[key] = groups[key] || []).push(t);
    });
    return `<div class="checks">${Object.entries(groups).map(([key, list]) => `<div class="group-title">${esc(owner[key] || key)}</div>${list.map((t) => check('types', `${esc(t.name)}${t.is_active ? '' : ' <span class="muted">(выключен)</span>'}`, selected.has(t.type_violation_id), t.type_violation_id)).join('')}`).join('')}</div>`;
  }

  async function editExecutor(id) {
    const [executors, types] = await Promise.all([ref('executors'), ref('types')]);
    const x = id ? executors.find((e) => e.executor_id === id) : null;
    const selected = new Set((x?.violation_types || []).map((v) => v.type_violation_id));
    openDialog({
      kicker: x ? x.executor_id : 'Новый исполнитель',
      title: x ? x.name : 'Организация-исполнитель',
      body: `<div class="grid-2">${input('name', 'Краткое название', x?.name, { required: true, attrs: 'minlength="2"' })}${select('kind', 'Вид', Object.entries(KIND), x?.kind || 'OMSU')}</div>` +
        input('full_name', 'Полное название', x?.full_name) +
        (x ? field('Ключ', `<div class="mono">${esc(x.code || '—')}</div>`, 'Ключ не меняется: по нему бот и аккаунт ведомства находят организацию.')
          : input('code', 'Ключ (латиницей)', '', { hint: 'Например, uk_levober. Станет логином аккаунта организации.', attrs: 'pattern="[a-z0-9_]+"' })) +
        field('Какие нарушения устраняет', typeChecks(types, executors, selected)) +
        check('is_active', 'Активен — DG принимает его в событиях', x ? x.is_active : true),
      onSubmit: async (fd) => {
        const body = { name: str(fd, 'name'), full_name: str(fd, 'full_name'), kind: str(fd, 'kind'), violation_type_ids: fd.getAll('types').map(String), is_active: fd.get('is_active') === 'on' };
        if (x) await api(`/executors/${encodeURIComponent(id)}`, { method: 'PATCH', body });
        else await api('/executors', { method: 'POST', body: { ...body, code: opt(fd, 'code') } });
        invalidate('executors', 'types');
        return x ? 'Исполнитель сохранён' : 'Исполнитель добавлен';
      },
    });
  }

  async function viewTypes() {
    const [types, executors] = await Promise.all([ref('types'), ref('executors')]);
    const write = can('references.write');
    const owners = {};
    executors.forEach((x) => x.violation_types.forEach((v) => { (owners[v.type_violation_id] = owners[v.type_violation_id] || []).push(x.name); }));
    const rows = types.map((t) => `<tr data-text="${rowText(t.type_violation_id, t.code, t.name, t.description, ...(owners[t.type_violation_id] || []))}">
      <td><strong>${esc(t.name)}</strong>${t.description ? `<span class="sub">${esc(t.description)}</span>` : ''}</td>
      <td class="mono small">${esc(t.code || '—')}<span class="sub">${esc(t.type_violation_id)}</span></td>
      <td>${(owners[t.type_violation_id] || []).map(esc).join(', ') || none('никто')}</td>
      <td>${t.requires_description ? 'да' : 'нет'}</td>
      <td>${activeBadge(t.is_active)}</td>
      <td class="actions">${write ? btn('type-edit', 'Изменить', { id: t.type_violation_id }) + btn('ref-delete', 'Удалить', { kind: 'types', id: t.type_violation_id, name: t.name }, 'danger small') : ''}</td></tr>`);
    return `<div class="toolbar"><p class="muted small">Тип без исполнителя DG не пропустит: в событии исполнитель и тип должны быть связаны.</p>${write ? btn('type-new', '+ Тип нарушения', {}, 'primary') : ''}</div>` +
      panel(`<div class="toolbar left">${search('types', 'Название, код, исполнитель')}</div>`,
        table(['Тип нарушения', 'Код / ID', 'Исполнители', 'Нужен комментарий', 'Статус', ''], rows, 'Типов нет'));
  }

  async function editType(id) {
    const t = id ? (await ref('types')).find((x) => x.type_violation_id === id) : null;
    openDialog({
      kicker: t ? t.type_violation_id : 'Новый тип',
      title: t ? t.name : 'Тип нарушения',
      body: input('name', 'Название', t?.name, { required: true, attrs: 'minlength="2"' }) +
        (t ? field('Код', `<div class="mono">${esc(t.code || '—')}</div>`) : input('code', 'Код', '', { hint: 'Как в боте: ведомство.проблема, например ekoprom.overflow' })) +
        textarea('description', 'Описание', t?.description) +
        check('requires_description', 'Инженер обязан написать комментарий', t ? t.requires_description : false) +
        check('is_active', 'Активен', t ? t.is_active : true) +
        (t ? '' : '<p class="muted small">Новый тип не заработает, пока его не отметят у исполнителя.</p>'),
      onSubmit: async (fd) => {
        const body = { name: str(fd, 'name'), description: str(fd, 'description'), requires_description: fd.get('requires_description') === 'on', is_active: fd.get('is_active') === 'on' };
        if (t) await api(`/violation-types/${encodeURIComponent(id)}`, { method: 'PATCH', body });
        else await api('/violation-types', { method: 'POST', body: { ...body, code: opt(fd, 'code') } });
        invalidate('types', 'executors');
        return t ? 'Тип сохранён' : 'Тип добавлен';
      },
    });
  }

  // ── Площадки КП ────────────────────────────────────────────────────────
  const KP_STATUS = {
    active: ['Действует', 'ok'],
    unverified: ['Не проверена', 'info'],
    planned: ['Планируется', 'violet'],
    relocated: ['Перенесена', 'warn'],
    liquidated: ['Ликвидирована', 'bad'],
    duplicate: ['Дубль', 'warn'],
    missing_in_source: ['Пропала из УТКО', 'bad'],
  };
  const KP_ROLE = { site_maintenance: 'Содержание площадки', waste_removal: 'Вывоз отходов', new_site_decision: 'Создание и перенос', territory: 'Прилегающая территория', supervision: 'Надзор' };
  const KP_SOURCE = { utko: 'ФГИС УТКО', omsu: 'реестр ОМСУ', operator: 'регоператор', field: 'полевая проверка', manual: 'вручную' };
  const KP_FIELD = {
    created: 'Карточка заведена', deleted: 'Удаление', location: 'Точка', status: 'Статус', area_m2: 'Площадь', containers: 'Контейнеры',
    responsibles: 'Ответственные', registry_number: 'Номер реестра', address_raw: 'Адрес', address_street: 'Ориентир: улица', address_house: 'Ориентир: дом',
    containers_qty: 'Число контейнеров', containers_volume_m3: 'Объём контейнеров', separate_collection: 'Раздельный сбор', kgo_storage: 'Хранение КГО',
    surface: 'Покрытие', has_fence: 'Ограждение', has_roof: 'Навес', in_yard: 'Во дворе МКД', land_parcel_cadnum: 'Кадастр участка', review_reason: 'Что проверить',
    name: 'Наименование', category: 'Категория', municipality: 'Муниципалитет', settlement: 'Населённый пункт', duplicate_of: 'Дубль карточки',
  };
  const SURFACE = { ASPHALT: 'асфальт', CONCRETE: 'бетон', SOIL: 'грунт' };
  const KP_BASIS = { rule: 'по правилу', manual: 'вручную', contract: 'договор', utko: 'ФГИС УТКО', field: 'проверка на месте' };
  const CONTAINER_TYPES = ['Для совместного накопления ТКО', 'Для раздельного накопления ТКО', 'Для крупногабаритных отходов'];
  const yesNo = (v) => (v === true ? 'да' : v === false ? 'нет' : '—');
  const kpPath = (key) => `/kp/${encodeURIComponent(key)}`;
  const histValue = (v, field) => {
    if (v === null || v === undefined || v === '') return '<span class="muted">—</span>';
    if (field === 'surface' && SURFACE[v]) return SURFACE[v];
    if (field === 'status' && KP_STATUS[v]) return KP_STATUS[v][0];
    if (Array.isArray(v) && v.length && typeof v[0] === 'object') return `${v.length} шт.`;
    if (typeof v === 'boolean') return v ? 'да' : 'нет';
    return esc(String(typeof v === 'object' ? JSON.stringify(v) : v).slice(0, 200));
  };

  async function viewKp(arg) {
    if (arg) return viewKpCard(arg);
    const f = state.filters.kp;
    const params = new URLSearchParams({ limit: state.limits.kp });
    if (state.kpQuery) params.set('q', state.kpQuery);
    if (f === 'review') params.set('review', 'true');
    else if (f === 'deleted') params.set('deleted', 'true');
    else if (f) params.set('status', f);
    const page = await api(`/kp/search?${params}`);
    const bs = page.by_status || {};
    const options = [['', 'Все', sum(bs)],
      ...Object.keys(KP_STATUS).filter((k) => bs[k] || f === k).map((k) => [k, KP_STATUS[k][0], bs[k] || 0]),
      ['review', 'На проверку', page.review], ['deleted', 'Удалённые', page.deleted]];
    const rows = page.items.map((k) => `<tr class="clickable" tabindex="0" data-href="#/kp/${encodeURIComponent(k.code)}">
      <td><strong class="mono">${esc(k.code)}</strong><span class="sub">${esc(k.name || '')}</span></td>
      <td class="wrap-anywhere">${esc(k.address || '—')}${k.review_reason ? `<span class="sub" style="color:var(--warning)">${esc(k.review_reason)}</span>` : ''}</td>
      <td class="mono small">${esc(k.registry_number || '—')}</td>
      <td class="num">${esc(k.containers_qty ?? '—')}<span class="sub">${k.containers_volume_m3 != null ? `${esc(k.containers_volume_m3)} м³` : ''}</span></td>
      <td>${badge(KP_STATUS, k.status)}</td></tr>`);
    const more = page.total > page.items.length && state.limits.kp < 500
      ? `<div class="panel-body" style="text-align:center">${btn('more', `Показать ещё (${page.items.length} из ${page.total})`, { key: 'kp' }, 'ghost')}</div>` : '';
    return `<div class="toolbar">${chips('kp', options)}${can('references.write') ? btn('kp-new', '+ Площадка', {}, 'primary') : ''}</div>
      <p class="muted small">Источник — ФГИС УТКО, слой мест накопления${page.last_sync_at ? `, последняя загрузка ${fmt(page.last_sync_at)}` : ''}. Правка вручную главнее выгрузки: следующая синхронизация её не перезапишет. Удалённая карточка остаётся в истории и восстанавливается.</p>` +
      panel(`<form class="toolbar left" data-form="kp-search"><input class="search" type="search" name="q" value="${esc(state.kpQuery)}" placeholder="Код LP-, адрес, номер реестра" aria-label="Поиск площадки"><button class="btn ghost small" type="submit">Найти</button></form><span class="muted small">показано ${page.items.length} из ${page.total}</span>`,
        table(['Площадка', 'Адрес', 'Реестр №', { t: 'Контейнеры', cls: 'num' }, 'Статус'], rows, 'Площадок не нашлось') + more);
  }

  async function viewKpCard(key) {
    const [k, hist] = await Promise.all([api(kpPath(key)), api(`${kpPath(key)}/history?limit=200`)]);
    $('#page-title').textContent = `${k.code} · ${k.address || 'площадка'}`;
    $('#page-subtitle').textContent = 'Карточка контейнерной площадки';
    const write = can('references.write');
    const src = (f) => (k.field_sources?.[f] ? `<span class="sub">${esc(KP_SOURCE[k.field_sources[f]] || k.field_sources[f])}</span>` : '');
    const d = { key: k.code };
    const actions = !write ? '' : k.deleted_at ? btn('kp-restore', 'Восстановить', d, 'primary small')
      : btn('kp-edit', 'Изменить', d) + btn('kp-containers', 'Контейнеры', d) + btn('kp-responsibles', 'Ответственные', d) +
        (k.verified_at ? '' : btn('kp-verify', 'Подтвердить на месте', d)) + btn('kp-delete', 'Удалить', d, 'danger small');
    const map = `https://www.openstreetmap.org/?mlat=${k.latitude}&mlon=${k.longitude}#map=19/${k.latitude}/${k.longitude}`;
    const passport = facts([
      ['Номер реестра', `<span class="mono">${esc(k.registry_number || '—')}</span>${src('registry_number')}`],
      ['Наименование', esc(k.name || '—')],
      ['Категория', esc(k.category || '—')],
      ['Адрес', `${esc(k.address || '—')}${k.address_street ? `<span class="sub">ориентир: ${esc(k.address_street)}${k.address_house ? `, ${esc(k.address_house)}` : ''}</span>` : ''}`],
      ['Точка', `<a class="mono" href="${esc(map)}" target="_blank" rel="noopener noreferrer">${esc(k.latitude)}, ${esc(k.longitude)}</a>${src('location')}`],
      ['Площадь', k.area_m2 != null ? `${esc(k.area_m2)} м²${src('area_m2')}` : '—'],
      ['Покрытие', esc(SURFACE[k.surface] || '—')],
      ['Ограждение / навес', `${yesNo(k.has_fence)} / ${yesNo(k.has_roof)}`],
      ['Раздельный сбор', yesNo(k.separate_collection)],
      ['Хранение КГО', esc(k.kgo_storage || '—')],
      ['Во дворе МКД', yesNo(k.in_yard)],
      ['Кадастр участка', `<span class="mono">${esc(k.land_parcel_cadnum || '—')}</span>`],
      ['Проверена на месте', k.verified_at ? `${fmt(k.verified_at)}<span class="sub">${esc(k.verified_by || '')}</span>` : none('нет')],
      ['Версия', `${esc(k.version)} · изменена ${fmt(k.updated_at)}`],
    ]);
    const containers = table(['№', 'Тип', 'Отходы', { t: 'Объём, м³', cls: 'num' }, 'Цвет'],
      k.containers.map((c) => `<tr><td class="mono">${esc(c.number || '—')}</td><td>${esc(c.container_type || '—')}</td><td>${esc(c.waste_group || '—')}</td><td class="num">${esc(c.volume_m3 ?? '—')}</td><td>${esc(c.color || '—')}</td></tr>`),
      'Контейнеров нет');
    const resp = k.responsibles.length
      ? `<ul class="media-list">${k.responsibles.map((r) => `<li><strong>${esc(KP_ROLE[r.role] || r.role)}</strong> — ${esc(r.executor_name)} <span class="muted small">${esc(KIND[r.kind] || r.kind)}</span>
          <span class="sub">${r.confirmed ? '<span style="color:var(--success)">подтверждено</span>' : '<span style="color:var(--warning)">не подтверждено</span>'} · основание: ${esc(KP_BASIS[r.basis] || r.basis || '—')}</span></li>`).join('')}</ul>`
      : '<p class="muted">Не назначены.</p>';
    const ext = k.external_ids.length
      ? facts(k.external_ids.map((e) => [KP_SOURCE[e.source] || e.source, `<code class="wrap-anywhere">${esc(e.external_id)}</code><span class="sub">в выгрузке ${fmt(e.last_seen_at)}</span>`]))
      : '<p class="muted">Заведена вручную.</p>';
    const cases = k.cases.total
      ? `${k.cases.total} ${plural(k.cases.total, 'дело', 'дела', 'дел')}, не закрыто ${k.cases.open}<span class="sub mono">№ ${k.cases.ids.map(esc).join(', ')}</span>`
      : none('дел не было');
    const histRows = hist.map((h) => `<tr><td>${fmt(h.changed_at)}<span class="sub mono">версия ${esc(h.version)}</span></td>
      <td>${h.field === 'deleted' && !h.new_value ? 'Восстановление' : esc(KP_FIELD[h.field] || h.field)}</td>
      <td class="small wrap-anywhere">${h.field === 'created' || h.field === 'deleted' ? '' : `${histValue(h.old_value, h.field)} → ${histValue(h.new_value, h.field)}`}</td>
      <td>${esc(KP_SOURCE[h.source] || h.source)}<span class="sub mono">${esc(h.actor)}</span></td>
      <td class="small">${h.applied ? '' : '<span class="badge warn">не применено</span> '}${esc(h.reason || '')}</td></tr>`);
    return `<a class="btn ghost small back" href="#/kp">← Все площадки</a>
      <div class="detail-hero"><div><span class="eyebrow">точка: ${esc(KP_SOURCE[k.location_source] || k.location_source)}</span><h2>${esc(k.code)} · ${esc(k.address || '')}</h2><code class="muted">${esc(k.kp_id)}</code></div>
        <div class="toolbar left">${badge(KP_STATUS, k.status)}${k.deleted_at ? '<span class="badge bad">Удалена</span>' : ''}${actions}</div></div>
      ${k.review_reason ? `<p class="form-error warn">Проверить: ${esc(k.review_reason)}</p>` : ''}
      <div class="split">${panel('<h2>Паспорт площадки</h2>', passport, { pad: true })}
        <div style="display:grid;gap:16px">${panel('<h2>Ответственные</h2>', resp, { pad: true })}${panel('<h2>Дела по площадке</h2>', `<p style="margin:0">${cases}</p>`, { pad: true })}${panel('<h2>Во внешних системах</h2>', ext, { pad: true })}</div></div>
      ${panel(`<h2>Контейнеры</h2><span class="muted small">${k.containers.length}${k.containers_closed ? ` · в истории ещё ${k.containers_closed}` : ''}</span>`, containers)}
      ${panel(`<h2>История карточки</h2><span class="muted small">${hist.length}</span>`, table(['Когда', 'Что', 'Было → стало', 'Кто', 'Примечание'], histRows, 'Изменений нет'))}`;
  }

  async function editKp(key) {
    const k = key ? await api(kpPath(key)) : null;
    const tri = (name, label, value) => select(name, label, [['true', 'да'], ['false', 'нет']], value === null || value === undefined ? '' : String(value), { empty: '—' });
    const num = (name, label, value, attrs) => input(name, label, value, { type: 'number', attrs: `step="any" ${attrs}` });
    openDialog({
      kicker: k ? k.code : 'Новая площадка',
      title: k ? (k.address || k.code) : 'Контейнерная площадка',
      body: input('address_raw', 'Адрес', k?.address, { required: true, hint: 'Как в реестре: «Перова ул, в районе д. 2 В» — из него берётся ориентир' }) +
        `<div class="grid-2">${num('latitude', 'Широта', k?.latitude, 'required min="-90" max="90"')}${num('longitude', 'Долгота', k?.longitude, 'required min="-180" max="180"')}</div>` +
        `<div class="grid-2">${input('registry_number', 'Номер реестра', k?.registry_number)}${select('status', 'Статус', Object.entries(KP_STATUS).map(([v, [t]]) => [v, t]), k?.status || 'unverified')}</div>` +
        `<div class="grid-2">${num('area_m2', 'Площадь, м²', k?.area_m2, 'min="0"')}${select('surface', 'Покрытие', Object.entries(SURFACE), k?.surface, { empty: '—' })}</div>` +
        `<div class="grid-4">${tri('has_fence', 'Ограждение', k?.has_fence)}${tri('has_roof', 'Навес', k?.has_roof)}${tri('separate_collection', 'Раздельный сбор', k?.separate_collection)}${tri('in_yard', 'Во дворе МКД', k?.in_yard)}</div>` +
        input('land_parcel_cadnum', 'Кадастровый номер участка', k?.land_parcel_cadnum) +
        (k ? textarea('review_reason', 'Что проверить', k.review_reason, 'Пусто — проверять нечего') + input('reason', 'Почему правка', '', { hint: 'Попадёт в историю карточки' }) : ''),
      onSubmit: async (fd) => {
        const n = (name) => (str(fd, name) === '' ? null : Number(str(fd, name)));
        const yes = (name) => (str(fd, name) === '' ? null : str(fd, name) === 'true');
        const body = {
          address_raw: str(fd, 'address_raw'), latitude: n('latitude'), longitude: n('longitude'), registry_number: opt(fd, 'registry_number'),
          status: str(fd, 'status'), area_m2: n('area_m2'), surface: opt(fd, 'surface'), has_fence: yes('has_fence'), has_roof: yes('has_roof'),
          separate_collection: yes('separate_collection'), in_yard: yes('in_yard'), land_parcel_cadnum: opt(fd, 'land_parcel_cadnum'),
        };
        if (!k) {
          Object.keys(body).forEach((name) => { if (body[name] === null) delete body[name]; });
          const created = await api('/kp', { method: 'POST', body });
          location.hash = `#/kp/${encodeURIComponent(created.code)}`;
          return `Площадка ${created.code} заведена`;
        }
        body.review_reason = opt(fd, 'review_reason');
        const was = { ...k, address_raw: k.address };
        const patch = Object.fromEntries(Object.entries(body).filter(([name, v]) => v !== (was[name] ?? null)));
        if ('latitude' in patch || 'longitude' in patch) Object.assign(patch, { latitude: body.latitude, longitude: body.longitude });
        if (!Object.keys(patch).length) return 'Изменений нет';
        patch.reason = opt(fd, 'reason');
        await api(kpPath(k.code), { method: 'PATCH', body: patch });
        return 'Карточка сохранена';
      },
    });
  }

  async function editKpContainers(key) {
    const k = await api(kpPath(key));
    const typeSelect = (value) => `<select name="c_type" aria-label="Тип"><option value="">—</option>${[...new Set([...CONTAINER_TYPES, ...(value ? [value] : [])])].map((t) => `<option ${t === value ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
    const row = (c = {}) => `<div class="ct-row"><input name="c_number" value="${esc(c.number ?? '')}" aria-label="Номер">${typeSelect(c.container_type)}
      <input name="c_waste" value="${esc(c.waste_group ?? '')}" aria-label="Группа отходов"><input name="c_volume" type="number" step="any" min="0" value="${esc(c.volume_m3 ?? '')}" aria-label="Объём"><input name="c_color" value="${esc(c.color ?? '')}" aria-label="Цвет"></div>`;
    openDialog({
      kicker: k.code,
      title: 'Контейнеры на площадке',
      body: `<div class="ct-row ct-head"><span>№</span><span>Тип</span><span>Группа отходов</span><span>м³</span><span>Цвет</span></div>${[...k.containers, {}, {}, {}].map(row).join('')}
        <p class="muted small">Пустые строки не сохраняются. Прежний состав уйдёт в историю, следующая выгрузка из УТКО его не перезапишет.</p>` +
        input('reason', 'Откуда данные', '', { hint: 'Например: проверка на месте 15.10' }),
      onSubmit: async (fd) => {
        const [num, type, waste, volume, color] = ['c_number', 'c_type', 'c_waste', 'c_volume', 'c_color'].map((name) => fd.getAll(name).map((v) => v.toString().trim()));
        const containers = num.map((_, i) => ({ number: num[i] || null, container_type: type[i] || null, waste_group: waste[i] || null, volume_m3: volume[i] === '' ? null : Number(volume[i]), color: color[i] || null }))
          .filter((c) => c.number || c.container_type || c.volume_m3 !== null);
        await api(`${kpPath(k.code)}/containers`, { method: 'PUT', body: { containers, reason: opt(fd, 'reason') } });
        return 'Контейнеры сохранены';
      },
    });
  }

  async function editKpResponsibles(key) {
    const [k, executors] = await Promise.all([api(kpPath(key)), ref('executors')]);
    const ex = executors.filter((x) => x.is_active).map((x) => [x.executor_id, `${x.name} · ${KIND[x.kind] || x.kind}`]);
    const pick = (name, options, value, label) => `<select name="${name}" aria-label="${esc(label)}"><option value="">—</option>${options.map(([v, t]) => `<option value="${esc(v)}" ${String(v) === String(value ?? '') ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
    const row = (r = {}) => `<div class="rs-row">${pick('r_role', Object.entries(KP_ROLE), r.role, 'Роль')}${pick('r_executor', ex, r.executor_id, 'Организация')}${pick('r_confirmed', [['true', 'подтверждено'], ['false', 'не подтверждено']], r.role ? String(r.confirmed) : 'false', 'Подтверждено')}</div>`;
    openDialog({
      kicker: k.code,
      title: 'Ответственные за площадку',
      body: `<div class="rs-row ct-head"><span>За что</span><span>Организация</span><span>Подтверждено</span></div>${[...k.responsibles, {}, {}].map(row).join('')}
        <p class="muted small">Подтверждено — документом или проверкой на месте. Вывоз по правилу — региональный оператор. Прежний состав уйдёт в историю.</p>
        ${textarea('reason', 'Почему правка', '', 'Попадёт в историю карточки')}`,
      onSubmit: async (fd) => {
        const [role, executor, confirmed] = ['r_role', 'r_executor', 'r_confirmed'].map((name) => fd.getAll(name).map(String));
        // Строка, которую не меняли, сохраняет прежнее основание («по правилу», «договор»)
        const basisOf = (r, x) => k.responsibles.find((p) => p.role === r && p.executor_id === x)?.basis || 'manual';
        const responsibles = role.map((_, i) => ({ role: role[i], executor_id: executor[i], confirmed: confirmed[i] === 'true', basis: basisOf(role[i], executor[i]) }))
          .filter((r) => r.role && r.executor_id);
        if (role.some((r, i) => Boolean(r) !== Boolean(executor[i]))) throw new Error('В каждой строке нужны и роль, и организация');
        await api(`${kpPath(k.code)}/responsibles`, { method: 'PUT', body: { responsibles, reason: opt(fd, 'reason') } });
        return 'Ответственные сохранены';
      },
    });
  }

  function kpAction(key, kind) {
    const conf = {
      delete: {
        title: 'Удалить площадку', submit: 'Удалить', danger: true,
        body: '<p>Карточка пропадёт из реестра и из «Диспетчерской». История и привязанные дела сохранятся, площадку можно восстановить.</p>' + textarea('reason', 'Причина', '', 'Попадёт в историю карточки'),
        run: (fd) => api(`${kpPath(key)}${opt(fd, 'reason') ? `?reason=${encodeURIComponent(opt(fd, 'reason'))}` : ''}`, { method: 'DELETE' }),
        done: 'Площадка удалена',
      },
      restore: { title: 'Восстановить площадку', submit: 'Восстановить', body: '<p>Карточка вернётся в реестр с прежней историей.</p>', run: () => api(`${kpPath(key)}/restore`, { method: 'POST' }), done: 'Площадка восстановлена' },
      verify: {
        title: 'Подтвердить на месте', submit: 'Подтвердить',
        body: '<p>Площадка проверена на месте: статус станет «Действует», в карточке появится дата проверки и ваш логин.</p>',
        run: () => api(kpPath(key), { method: 'PATCH', body: { verified: true } }), done: 'Площадка подтверждена',
      },
    }[kind];
    openDialog({ kicker: key, title: conf.title, body: conf.body, submit: conf.submit, danger: conf.danger, onSubmit: async (fd) => { await conf.run(fd); return conf.done; } });
  }

  // ── Удаление записей справочников ──────────────────────────────────────
  const REF_DELETE = {
    engineers: ['/engineers', 'инженера', ['engineers', 'assignments']],
    territories: ['/territories', 'участок', ['territories', 'assignments', 'engineers']],
    assignments: ['/assignments', 'назначение', ['assignments', 'engineers']],
    executors: ['/executors', 'исполнителя', ['executors', 'types']],
    types: ['/violation-types', 'тип нарушения', ['types', 'executors']],
  };

  function deleteRef(kind, id, name) {
    const [path, what, caches] = REF_DELETE[kind];
    openDialog({
      kicker: id,
      title: `Удалить ${what}`,
      body: `<p>Удалить <strong>${esc(name)}</strong> насовсем?</p>
        <p class="muted">Удалять стоит только запись, заведённую по ошибке. Если на неё ссылаются дела, назначения, пользователи или площадки, CRM откажет — такую запись выключают (снимите «Активен» в карточке).</p>`,
      submit: 'Удалить',
      danger: true,
      onSubmit: async () => {
        await api(`${path}/${encodeURIComponent(id)}`, { method: 'DELETE' });
        invalidate(...caches);
        return 'Удалено';
      },
    });
  }

  // ── Пользователи и роли ────────────────────────────────────────────────
  async function viewUsers() {
    const [users, roles, executors] = await Promise.all([ref('users'), ref('roles'), can('references.read') ? ref('executors') : Promise.resolve([])]);
    const roleName = Object.fromEntries(roles.map((r) => [r.code, r.name]));
    const ex = byId(executors, 'executor_id');
    const rows = users.map((u) => `<tr data-text="${rowText(u.username, u.full_name, ...u.roles.map((r) => roleName[r] || r), ex[u.executor_id]?.name)}">
      <td><strong class="mono">${esc(u.username)}</strong><span class="sub">${esc(u.full_name || '')}</span></td>
      <td>${u.roles.map((r) => `<span class="tag">${esc(roleName[r] || r)}</span>`).join('') || none('без ролей')}</td>
      <td>${u.executor_id ? esc(ex[u.executor_id]?.name || u.executor_id) : '<span class="muted">все дела</span>'}</td>
      <td>${u.role ? esc(FRONT_ROLE[u.role]) : none('нет доступа')}</td>
      <td>${fmt(u.last_login_at)}</td>
      <td>${activeBadge(u.is_active, 'Отключён')}</td>
      <td class="actions">${btn('user-edit', 'Изменить', { id: u.id })}</td></tr>`);
    return `<div class="toolbar"><p class="muted small">Один логин — и для «Диспетчерской», и для этой консоли. Что видно в консоли, решают права ролей.</p>${btn('user-new', '+ Пользователь', {}, 'primary')}</div>` +
      panel(`<div class="toolbar left">${search('users', 'Логин, имя, роль, организация')}</div>`,
        table(['Логин', 'Роли', 'Организация', '«Диспетчерская»', 'Последний вход', 'Статус', ''], rows, 'Пользователей нет'));
  }

  function newPassword() {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
    const bytes = new Uint32Array(16);
    crypto.getRandomValues(bytes);
    return [...bytes].map((b) => alphabet[b % alphabet.length]).join('');
  }

  async function editUser(id) {
    const [users, roles, executors] = await Promise.all([ref('users'), ref('roles'), can('references.read') ? ref('executors') : Promise.resolve([])]);
    const u = id ? users.find((x) => String(x.id) === String(id)) : null;
    const mine = new Set(u?.roles || []);
    const roleChecks = `<div class="checks">${roles.map((r) => check('roles', `<strong>${esc(r.name)}</strong> <span class="muted mono small">${esc(r.code)}</span>${r.description ? `<br><span class="muted small">${esc(r.description)}</span>` : ''}`, mine.has(r.code), r.code)).join('')}</div>`;
    const self = u && u.id === state.me.id;
    openDialog({
      kicker: u ? `Пользователь № ${u.id}` : 'Новый пользователь',
      title: u ? u.username : 'Учётная запись',
      body: (u ? field('Логин', `<div class="mono">${esc(u.username)}</div>`) : input('username', 'Логин', '', { required: true, hint: 'Латиница, цифры, точка, дефис, подчёркивание', attrs: 'minlength="3" pattern="[a-zA-Z0-9_.\\-]+"' })) +
        input('full_name', 'Имя или название', u?.full_name) +
        field(u ? 'Новый пароль' : 'Пароль', `<div class="input-row"><input name="password" type="text" autocomplete="new-password" ${u ? '' : 'required'} minlength="10" spellcheck="false"><button type="button" class="btn ghost small" data-action="gen-password">Придумать</button></div>`,
          u ? 'Пусто — пароль не меняется. Смена пароля завершает все сеансы пользователя.' : 'Не короче 10 символов. Передайте его пользователю сами.') +
        field('Роли', roleChecks) +
        select('executor_id', 'Организация', executors.map((x) => [x.executor_id, x.name]), u?.executor_id, { empty: '— без организации: видит все дела —', hint: 'Исполнителю (роль «Исполнитель», «Мастер УК») организация обязательна: он видит только её дела.' }) +
        (self ? '<p class="muted small">Это вы: отключить себя и снять с себя роль системного администратора нельзя.</p>'
          : check('is_active', 'Активен — может входить', u ? u.is_active : true)),
      onSubmit: async (fd) => {
        const password = str(fd, 'password');
        if (password && password.length < 10) throw new Error('Пароль не короче 10 символов');
        const body = { full_name: str(fd, 'full_name'), roles: fd.getAll('roles').map(String), executor_id: opt(fd, 'executor_id') };
        if (!self) body.is_active = fd.get('is_active') === 'on';
        if (password) body.password = password;
        if (u) await api(`/users/${encodeURIComponent(u.id)}`, { method: 'PATCH', body });
        else await api('/users', { method: 'POST', body: { username: str(fd, 'username'), ...body } });
        invalidate('users');
        return u ? (password ? 'Сохранено, пароль сменён' : 'Сохранено') : 'Пользователь добавлен — передайте ему пароль';
      },
    });
  }

  async function viewRoles() {
    const [roles, permissions, users] = await Promise.all([ref('roles'), ref('permissions'), ref('users')]);
    const permName = Object.fromEntries(permissions.map((p) => [p.code, p.name]));
    const holders = {};
    users.forEach((u) => u.roles.forEach((r) => { holders[r] = (holders[r] || 0) + 1; }));
    const cards = roles.map((r) => panel(
      `<div><h2>${esc(r.name)}</h2><span class="muted mono small">${esc(r.code)}</span></div><div>${r.is_system ? '<span class="badge info">системная</span> ' : ''}${btn('role-edit', 'Изменить', { code: r.code })}</div>`,
      `${r.description ? `<p class="muted">${esc(r.description)}</p>` : ''}
       <p class="small muted">Пользователей: ${holders[r.code] || 0}</p>
       <ul class="perm-list">${r.permissions.map((p) => `<li>${esc(permName[p] || p)}</li>`).join('') || '<li>прав нет</li>'}</ul>`,
      { pad: true },
    ).replace('class="panel"', 'class="panel role-card"'));
    return `<div class="toolbar"><p class="muted small">Права системного администратора меняются только в коде CRM; остальные роли — здесь.</p>${btn('role-new', '+ Роль', {}, 'primary')}</div><div class="role-grid">${cards.join('')}</div>`;
  }

  async function editRole(code) {
    const [roles, permissions] = await Promise.all([ref('roles'), ref('permissions')]);
    const r = code ? roles.find((x) => x.code === code) : null;
    const locked = r?.code === 'admin';
    const mine = new Set(r?.permissions || []);
    const perms = `<div class="checks">${permissions.map((p) => check('permissions', `${esc(p.name)} <span class="muted mono small">${esc(p.code)}</span>`, mine.has(p.code), p.code)).join('')}</div>`;
    openDialog({
      kicker: r ? r.code : 'Новая роль',
      title: r ? r.name : 'Роль',
      body: (r ? '' : input('code', 'Код', '', { required: true, hint: 'Латиницей, например uk_viewer', attrs: 'pattern="[a-z][a-z0-9_]+"' })) +
        input('name', 'Название', r?.name, { required: true, attrs: 'minlength="2"' }) +
        textarea('description', 'Описание', r?.description) +
        (locked ? '<p class="muted small">У системного администратора все права, они меняются только в коде.</p>' : field('Права', perms)),
      onSubmit: async (fd) => {
        const body = { name: str(fd, 'name'), description: str(fd, 'description') };
        if (!locked) body.permissions = fd.getAll('permissions').map(String);
        if (r) await api(`/roles/${encodeURIComponent(code)}`, { method: 'PATCH', body });
        else await api('/roles', { method: 'POST', body: { code: str(fd, 'code'), ...body } });
        invalidate('roles', 'users');
        return r ? 'Роль сохранена' : 'Роль добавлена';
      },
    });
  }

  // ── Журнал ─────────────────────────────────────────────────────────────
  async function viewAudit() {
    const items = await api('/audit?limit=500');
    const rows = items.map((a) => {
      const detail = a.detail && Object.keys(a.detail).length ? JSON.stringify(a.detail) : '';
      return `<tr data-text="${rowText(a.actor, a.action, AUDIT[a.action], a.entity, a.entity_id, detail)}">
        <td>${fmt(a.at)}</td>
        <td class="mono">${esc(a.actor)}</td>
        <td>${esc(AUDIT[a.action] || a.action)}<span class="sub mono">${esc(a.action)}</span></td>
        <td>${esc(a.entity)}<span class="sub mono">${esc(a.entity_id || '')}</span></td>
        <td class="mono small wrap-anywhere">${esc(detail.slice(0, 300))}</td></tr>`;
    });
    return panel(`<div class="toolbar left">${search('audit', 'Кто, действие, объект')}</div><span class="muted small">последние ${items.length}</span>`,
      table(['Когда', 'Кто', 'Действие', 'Объект', 'Подробности'], rows, 'Журнал пуст'));
  }

  // ── Data Gateway ───────────────────────────────────────────────────────
  async function viewDg() {
    const i = await api('/integration/datagateway');
    const endpoints = [
      ['GET', '/api/v1/integration/engineers', 'инженеры'],
      ['GET', '/api/v1/integration/executors', 'исполнители и их типы'],
      ['GET', '/api/v1/integration/violation-types/{id}', 'тип нарушения'],
      ['GET', '/api/v1/integration/assignments/bot-users/{max_user_id}', 'кто этот пользователь MAX'],
      ['GET', '/api/v1/integration/assignments/engineers/{id}/current', 'текущий участок инженера'],
      ['POST', '/api/v1/integration/bot-users/registrations', 'регистрация из бота'],
      ['POST', '/api/v1/integrations/datagateway/configure', 'сопряжение'],
      ['POST', '/api/v1/integrations/datagateway/events', 'приём событий (подпись HMAC)'],
    ];
    return `<div class="split">
      ${panel('<h2>Подключение</h2>', dgFacts(i), { pad: true })}
      ${panel('<h2>Как подключить</h2>', `<ol style="margin:0;padding-left:20px;display:grid;gap:6px">
        <li>В Data Gateway: «API-подключения → Потребители» → «Подключить CRM».</li>
        <li>Адрес CRM: в одной Docker-сети с DG — <code>http://chisto-crm:8000</code>.</li>
        <li>Setup-токен — значение <code>CRM_DG_WRITE_TOKEN</code> из <code>.env</code> CRM.</li>
        <li>DG сам пришлёт ключ подписи; статус обновится здесь.</li></ol>
        <p class="muted small" style="margin-top:10px">Справочники DG читает с токеном <code>CRM_DG_READ_TOKEN</code>, регистрацию шлёт с <code>CRM_DG_WRITE_TOKEN</code>.</p>`, { pad: true })}
    </div>` + panel('<h2>Что CRM отдаёт Data Gateway</h2><span class="muted small">контракт DG v1</span>',
      table(['Метод', 'Путь', 'Зачем'], endpoints.map(([m, p, w]) => `<tr><td class="mono">${m}</td><td><code class="wrap-anywhere">${esc(p)}</code></td><td>${esc(w)}</td></tr>`)));
  }

  const VIEWS = {
    overview: viewOverview,
    events: viewEvents,
    cases: viewCases,
    registrations: viewRegistrations,
    engineers: viewEngineers,
    territories: viewTerritories,
    assignments: viewAssignments,
    executors: viewExecutors,
    types: viewTypes,
    kp: viewKp,
    users: viewUsers,
    roles: viewRoles,
    audit: viewAudit,
    dg: viewDg,
  };

  // ── События интерфейса ─────────────────────────────────────────────────
  const ACTIONS = {
    filter: (d) => { state.filters[d.key] = d.value; render(); },
    more: (d) => { state.limits[d.key] = Math.min(500, state.limits[d.key] + 50); render(); },
    goto: (d) => { state.search[d.view] = d.q; if (location.hash === `#/${d.view}`) render(); else location.hash = `#/${d.view}`; },
    'reg-resolve': (d) => resolveRegistration(d.id),
    'reg-reject': (d) => rejectRegistration(d.id),
    'engineer-new': () => editEngineer(null),
    'engineer-edit': (d) => editEngineer(d.id),
    'engineer-assign': (d) => editAssignment(null, d.id),
    'engineer-unlink': (d) => unlinkMax(d.id),
    'territory-new': () => editTerritory(null),
    'territory-edit': (d) => editTerritory(d.id),
    'assignment-new': () => editAssignment(null),
    'assignment-edit': (d) => editAssignment(d.id),
    'executor-new': () => editExecutor(null),
    'executor-edit': (d) => editExecutor(d.id),
    'type-new': () => editType(null),
    'type-edit': (d) => editType(d.id),
    'ref-delete': (d) => deleteRef(d.kind, d.id, d.name),
    'kp-new': () => editKp(null),
    'kp-edit': (d) => editKp(d.key),
    'kp-containers': (d) => editKpContainers(d.key),
    'kp-responsibles': (d) => editKpResponsibles(d.key),
    'kp-verify': (d) => kpAction(d.key, 'verify'),
    'kp-delete': (d) => kpAction(d.key, 'delete'),
    'kp-restore': (d) => kpAction(d.key, 'restore'),
    'user-new': () => editUser(null),
    'user-edit': (d) => editUser(d.id),
    'role-new': () => editRole(null),
    'role-edit': (d) => editRole(d.code),
    'gen-password': (_, el) => {
      const field = el.closest('.input-row').querySelector('input');
      field.value = newPassword();
      field.select();
    },
  };

  document.addEventListener('click', async (event) => {
    const actionEl = event.target.closest('[data-action]');
    if (actionEl && ACTIONS[actionEl.dataset.action]) {
      event.preventDefault();
      try {
        await ACTIONS[actionEl.dataset.action](actionEl.dataset, actionEl);
      } catch (err) {
        if (!(err instanceof AuthError)) toast(err.message, true);
      }
      return;
    }
    const row = event.target.closest('tr[data-href]');
    if (row && !event.target.closest('a, button')) location.hash = row.dataset.href;
  });
  document.addEventListener('keydown', (event) => {
    const row = event.target.closest?.('tr[data-href]');
    if (row && event.key === 'Enter') location.hash = row.dataset.href;
  });
  content.addEventListener('input', (event) => {
    const el = event.target.closest('[data-search]');
    if (!el) return;
    state.search[el.dataset.search] = el.value;
    filterRows(el, el.value);
  });
  // Поиск площадок идёт на сервере: их тысячи, в таблицу приходит одна страница
  content.addEventListener('submit', (event) => {
    const form = event.target.closest('form[data-form="kp-search"]');
    if (!form) return;
    event.preventDefault();
    state.kpQuery = new FormData(form).get('q').toString().trim();
    state.limits.kp = 50;
    render();
  });
  window.addEventListener('hashchange', render);

  $('#theme').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('crm-admin-theme', next); } catch { /* хранилище недоступно — тема до перезагрузки */ }
  });

  $('#logout').addEventListener('click', async () => {
    try { await api('/auth/logout', { method: 'POST' }); } catch { /* выходим в любом случае */ }
    showLogin('');
  });

  $('#login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    const button = $('button[type=submit]', event.target);
    const err = $('#login-error');
    button.disabled = true;
    err.hidden = true;
    try {
      await api('/auth/login', { method: 'POST', body: { username: str(fd, 'username'), password: fd.get('password') } });
      event.target.reset();
      start(await api('/auth/me'));
    } catch (e) {
      if (e instanceof AuthError) return;
      err.textContent = e.message === 'Неверный логин или пароль' || /401/.test(e.message) ? 'Неверный логин или пароль' : e.message;
      err.hidden = false;
    } finally {
      button.disabled = false;
    }
  });

  // ── Старт ──────────────────────────────────────────────────────────────
  (async () => {
    try {
      start(await api('/auth/me'));
    } catch (err) {
      if (!(err instanceof AuthError)) showLogin(err.message);
    }
  })();
})();

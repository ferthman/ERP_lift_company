let savedIdentity = null;
try { savedIdentity = JSON.parse(localStorage.getItem('liftcrm-mobile-identity') || 'null'); } catch (_) {}
const mobileIdentity = window.MOBILE_BOOTSTRAP?.userId
  ? { id: window.MOBILE_BOOTSTRAP.userId, username: window.MOBILE_BOOTSTRAP.username }
  : window.MOBILE_BOOTSTRAP?.offlineShell ? savedIdentity : null;
const DB_NAME = `liftcrm-mobile-${mobileIdentity?.id || 'locked'}`;
let syncPromise = null, queueBusy = false;
function lockMobile() {
  state.authBlocked = true;
  document.getElementById('mobile-auth')?.classList.remove('hidden');
  document.getElementById('mobile-workspace')?.classList.add('hidden');
}
async function mobileFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('X-Mobile-User', String(mobileIdentity?.id || 'locked'));
  let res;
  try {res=await fetch(url, { ...options, headers, cache: 'no-store' });}
  catch(err){state.online=false;throw err;}
  if (res.status === 401 || (res.status === 409 && (await res.clone().json())?.error?.code === 'IDENTITY_CHANGED')) {
    lockMobile();
    throw new Error('Войдите под своей учётной записью');
  }
  return res;
}
async function verifyIdentity() {
  if (!mobileIdentity?.id) { lockMobile(); return false; }
  try {
    const res = await mobileFetch('/api/me');
    const me = await res.json();
    if (!me.authenticated || me.id !== mobileIdentity.id || me.role !== 'technician') { lockMobile(); return false; }
    return true;
  } catch (_) { if(state.authBlocked)return false;state.online=false;return true; }
}
const DB_VERSION = 2;
const MAX_PHOTO_SIZE_BYTES = 8 * 1024 * 1024;
const MAX_QUEUED_PHOTOS = 20;
const CLOSE_REASONS = [
  "EQUIPMENT_FAILURE",
  "PASSENGER_TRAPPED",
  "FALSE_CALL",
  "POWER_ISSUE",
  "EXTERNAL_REASON",
  "OTHER",
];
const STATUS_RU = {
  NEW: "Новая",
  ASSIGNED: "Назначена",
  ACCEPTED: "Принята",
  IN_PROGRESS: "В работе",
  WAITING: "Ожидание",
  COMPLETED: "Завершена",
  CANCELLED: "Отменена",
};
const PRIORITY_RU = {
  EMERGENCY: "Аварийная",
  HIGH: "Высокая",
  MEDIUM: "Обычная",
  LOW: "Низкая",
};
const PRIORITY_STYLES = {
  EMERGENCY: "bg-red-600 text-white",
  HIGH: "bg-amber-100 text-amber-800",
  MEDIUM: "bg-slate-200 text-slate-700",
  LOW: "bg-slate-100 text-slate-500",
};
const EVENT_TYPE_RU = {
  TICKET_ACCEPT: "Принятие заявки",
  TICKET_IN_PROGRESS: "В работу",
  TICKET_WAITING: "Ожидание",
  TICKET_DONE: "Завершение",
  TICKET_ADD_COMMENT: "Комментарий",
};
const SYNC_ERROR_RU = {
  ARCHIVED: "Заявка архивирована",
  CONFLICT: "Заявка изменилась на сервере",
  FORBIDDEN: "Заявка больше не назначена вам",
  IMMUTABLE: "Заявка закрыта",
  INVALID_EVENT: "Некорректное действие",
  NO_TARGET_COORDS: "У заявки нет координат объекта",
  NO_TECH_COORDS: "Нет координат мастера",
  NOT_FOUND: "Заявка не найдена",
  OUT_OF_RANGE: "Вы вне геозоны объекта",
  SERVER_ERROR: "Ошибка сервера",
  VALIDATION_ERROR: "Проверьте данные действия",
};

const state = {
  tickets: [],
  selectedId: null,
  historyItems: [],
  historySelectedId: null,
  historyUpdatedAt: null,
  historyOffline: false,
  online: navigator.onLine,
  pendingCount: 0,
  errorCount: 0,
  pendingPhotoCount: 0,
  errorPhotoCount: 0,
  lastSync: null,
};

const elements = {
  list: document.getElementById("tickets-list"),
  detail: document.getElementById("ticket-detail"),
  syncStatus: document.getElementById("sync-status"),
  lastSync: document.getElementById("last-sync"),
  ticketStatus: document.getElementById("ticket-status"),
  ticketDetailCard: document.getElementById("ticket-detail-card"),
  tabTickets: document.getElementById("tab-tickets"),
  tabHistory: document.getElementById("tab-history"),
  ticketsPanel: document.getElementById("tickets-panel"),
  historyPanel: document.getElementById("history-panel"),
  historyList: document.getElementById("history-list"),
  historyDetailCard: document.getElementById("history-detail-card"),
  historyDetail: document.getElementById("history-detail"),
  historyDetailStatus: document.getElementById("history-detail-status"),
  historyDateFrom: document.getElementById("history-date-from"),
  historyDateTo: document.getElementById("history-date-to"),
  historyApply: document.getElementById("history-apply"),
  historyOffline: document.getElementById("history-offline"),
  historyUpdated: document.getElementById("history-updated"),
  btnSync: document.getElementById("btn-sync"),
  btnReset: document.getElementById("btn-reset"),
  outboxPanel: document.getElementById("outbox-panel"),
  outboxFailedList: document.getElementById("outbox-failed-list"),
  outboxRetryAll: document.getElementById("outbox-retry-all"),
};

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("ru-RU");
  } catch (err) {
    return value;
  }
}

function getStatusLabel(status) {
  if (!status) return "—";
  return STATUS_RU[status] || status;
}

function normalizePriority(priority) {
  return String(priority || "MEDIUM").toUpperCase();
}

function getPriorityLabel(priority) {
  const key = normalizePriority(priority);
  return PRIORITY_RU[key] || key;
}

function renderPriorityBadge(priority) {
  const key = normalizePriority(priority);
  const style = PRIORITY_STYLES[key] || PRIORITY_STYLES.MEDIUM;
  return `<span class="text-xs font-semibold px-2 py-1 rounded-full ${style}">${escapeHtml(getPriorityLabel(key))}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function uid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(Number(c)^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Number(c)/4).toString(16));
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("tickets_list_cache")) {
        db.createObjectStore("tickets_list_cache", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("tickets_cache")) {
        db.createObjectStore("tickets_cache", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("history_list_cache")) {
        db.createObjectStore("history_list_cache", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("history_timeline_cache")) {
        db.createObjectStore("history_timeline_cache", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("outbox_events")) {
        db.createObjectStore("outbox_events", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("outbox_photos")) {
        db.createObjectStore("outbox_photos", { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore(storeName, mode, callback) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    let requestResult;
    let request;
    try {
      request = callback(store);
    } catch (err) {
      reject(err);
      return;
    }
    if (request && typeof request.addEventListener === "function") {
      request.onsuccess = () => {
        requestResult = request.result;
      };
      request.onerror = () => reject(request.error);
    }
    tx.oncomplete = () => { db.close(); resolve(requestResult); };
    tx.onerror = () => { db.close(); reject(tx.error); };
  });
}

async function saveListCache(items) {
  return withStore("tickets_list_cache", "readwrite", (store) =>
    store.put({ id: "list", items, updated_at: new Date().toISOString() })
  );
}

async function loadListCache() {
  const entry = await withStore("tickets_list_cache", "readonly", (store) => store.get("list"));
  return entry?.items || [];
}

async function saveTicketCache(ticket) {
  return withStore("tickets_cache", "readwrite", (store) => store.put(ticket));
}

async function loadTicketCache(id) {
  return withStore("tickets_cache", "readonly", (store) => store.get(id));
}

async function saveHistoryListCache(items, filters) {
  return withStore("history_list_cache", "readwrite", (store) =>
    store.put({ id: "last", items, filters: filters || {}, updated_at: new Date().toISOString() })
  );
}

async function loadHistoryListCache() {
  return withStore("history_list_cache", "readonly", (store) => store.get("last"));
}

async function saveHistoryTimelineCache(ticketId, items) {
  return withStore("history_timeline_cache", "readwrite", (store) =>
    store.put({ id: String(ticketId), items, updated_at: new Date().toISOString() })
  );
}

async function loadHistoryTimelineCache(ticketId) {
  return withStore("history_timeline_cache", "readonly", (store) => store.get(String(ticketId)));
}

async function listOutboxEvents() {
  return withStore("outbox_events", "readonly", (store) => store.getAll());
}

async function putOutboxEvent(event) {
  return withStore("outbox_events", "readwrite", (store) => store.put(event));
}

async function deleteOutboxEvent(id) {
  return withStore("outbox_events", "readwrite", (store) => store.delete(id));
}

async function listOutboxPhotos() {
  return withStore("outbox_photos", "readonly", (store) => store.getAll());
}

async function putOutboxPhoto(photo) {
  return withStore("outbox_photos", "readwrite", (store) => store.put(photo));
}

async function deleteOutboxPhoto(id) {
  return withStore("outbox_photos", "readwrite", (store) => store.delete(id));
}

function getEventLabel(event) {
  return EVENT_TYPE_RU[event?.type] || event?.type || "Действие";
}

function getErrorLabel(error) {
  const code = error?.code || "ERROR";
  const message = error?.message || SYNC_ERROR_RU[code] || "Не удалось синхронизировать";
  return `${SYNC_ERROR_RU[code] || message}${message && message !== SYNC_ERROR_RU[code] ? `: ${message}` : ""}`;
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  return `${Math.ceil(bytes / 1024)} КБ`;
}

async function updateSyncIndicators() {
  const events = await listOutboxEvents();
  const photos = await listOutboxPhotos();
  state.pendingCount = events.filter((e) => e.status === "pending").length;
  state.errorCount = events.filter((e) => e.status === "error").length;
  state.pendingPhotoCount = photos.filter((p) => p.status === "pending").length;
  state.errorPhotoCount = photos.filter((p) => p.status === "error").length;
  const totalPending = state.pendingCount + state.pendingPhotoCount;
  const totalErrors = state.errorCount + state.errorPhotoCount;
  const online = state.online;
  let text = "—";
  if (!online) {
    text = totalPending > 0 ? `Оффлайн • В очереди ${totalPending}` : "Оффлайн";
  } else if (totalErrors > 0) {
    text = `Ошибка (${totalErrors})`;
  } else if (totalPending > 0) {
    text = `В очереди ${totalPending}`;
  } else {
    text = "Синхронизировано";
  }
  elements.syncStatus.textContent = text;
  document.querySelectorAll('.mobile-detail-sync').forEach(el=>el.textContent=text);
  elements.lastSync.textContent = state.lastSync ? `Последняя синхронизация: ${formatDate(state.lastSync)}` : "—";
  await renderFailedOutbox(events, photos);
}

async function retryOutboxEvent(id) {
  const events = await listOutboxEvents();
  const event = events.find((item) => item.id === id);
  if (!event) return;
  event.status = "pending";
  event.error = null;
  event.retry_at = new Date().toISOString();
  await putOutboxEvent(event);
  await updateSyncIndicators();
  await syncAll();
}

async function discardOutboxEvent(id) {
  if(!state.online){alert('Подключитесь к сети, чтобы восстановить актуальное состояние заявки.');return;}
  const events=await listOutboxEvents();
  const event=events.find(item=>item.id===id);
  if(!event)return;
  const dependent=events.filter(item=>item.ticket_id===event.ticket_id && item.expected_version>=event.expected_version);
  if(!confirm(`Удалить действие и следующие за ним изменения этой заявки (${dependent.length})? Они не будут отправлены. Будет загружено состояние с сервера. Фото сохранятся в очереди.`))return;
  let current;
  try {
    const response=await mobileFetch(`/api/tickets/${event.ticket_id}`);
    if(response.ok)current=await response.json();
    else if(![403,404].includes(response.status))throw new Error();
  } catch(_){alert('Не удалось проверить заявку. Очередь сохранена, попробуйте после восстановления связи.');return;}
  for(const item of dependent)await deleteOutboxEvent(item.id);
  if(current)await saveTicketCache(current);
  else await withStore('tickets_cache','readwrite',store=>store.delete(event.ticket_id));
  await refreshTickets();
  if(state.selectedId===event.ticket_id){if(current)renderDetail(current);else elements.ticketDetailCard?.classList.add('hidden');}
  await updateSyncIndicators();
}

async function retryOutboxPhoto(id) {
  const photos = await listOutboxPhotos();
  const photo = photos.find((item) => item.id === id);
  if (!photo) return;
  photo.status = "pending";
  photo.error = null;
  photo.retry_at = new Date().toISOString();
  await putOutboxPhoto(photo);
  await updateSyncIndicators();
  await syncAll();
}

async function discardOutboxPhoto(id) {
  if(!confirm("Удалить неотправленное фото из очереди?"))return;
  await deleteOutboxPhoto(id);
  await updateSyncIndicators();
  if (state.selectedId) {
    await renderPhotoQueue(state.selectedId);
  }
}

async function retryAllFailedOutbox() {
  const events = await listOutboxEvents();
  for (const event of events.filter((item) => item.status === "error")) {
    event.status = "pending";
    event.error = null;
    event.retry_at = new Date().toISOString();
    await putOutboxEvent(event);
  }
  const photos = await listOutboxPhotos();
  for (const photo of photos.filter((item) => item.status === "error")) {
    photo.status = "pending";
    photo.error = null;
    photo.retry_at = new Date().toISOString();
    await putOutboxPhoto(photo);
  }
  await updateSyncIndicators();
  await syncAll();
}

async function renderFailedOutbox(events, photos) {
  if (!elements.outboxPanel || !elements.outboxFailedList) return;
  const failedEvents = (events || []).filter((event) => event.status === "error");
  const failedPhotos = (photos || []).filter((photo) => photo.status === "error");
  const failed = [
    ...failedEvents.map((event) => ({ kind: "event", item: event })),
    ...failedPhotos.map((photo) => ({ kind: "photo", item: photo })),
  ];
  elements.outboxPanel.classList.toggle("hidden", failed.length === 0);
  elements.outboxFailedList.innerHTML = "";
  failed.forEach(({ kind, item }) => {
    const row = document.createElement("div");
    row.className = "rounded-lg border border-amber-200 bg-white p-2 text-xs text-amber-950";
    const title =
      kind === "event"
        ? `${getEventLabel(item)} · заявка #${item.ticket_id}`
        : `Фото · заявка #${item.ticket_id}`;
    const detail = kind === "event" ? getErrorLabel(item.error) : getErrorLabel(item.error);
    row.innerHTML = `
      <div class="font-semibold">${escapeHtml(title)}</div>
      <div class="mt-1">${escapeHtml(detail)}</div>
      <div class="mt-2 flex gap-2">
        <button class="retry px-2 py-1 rounded bg-amber-900 text-white">Повторить</button>
        <button class="discard px-2 py-1 rounded bg-white ring-1 ring-amber-300">Удалить из очереди</button>
      </div>
    `;
    row.querySelector(".retry")?.addEventListener("click", () => {
      if (kind === "event") {
        retryOutboxEvent(item.id);
      } else {
        retryOutboxPhoto(item.id);
      }
    });
    row.querySelector(".discard")?.addEventListener("click", () => {
      if (kind === "event") {
        discardOutboxEvent(item.id);
      } else {
        discardOutboxPhoto(item.id);
      }
    });
    elements.outboxFailedList.appendChild(row);
  });
}

function updateTicketStatusBadge(ticket) {
  if (!elements.ticketStatus) return;
  if (!ticket) {
    elements.ticketStatus.textContent = "—";
    return;
  }
  elements.ticketStatus.textContent = `№ ${ticket.id} · ${getStatusLabel(ticket.status)} · ${getPriorityLabel(ticket.priority)}`;
}

function renderList() {
  if (!elements.list) return;
  const active = state.tickets.filter(t=>!['COMPLETED','CANCELLED'].includes(t.status));
  const counters = document.getElementById('mobile-counters');
  if(counters) counters.innerHTML = `<div class="mobile-counter"><strong>${active.length}</strong><small>Активных</small></div><div class="mobile-counter"><strong>${active.filter(t=>t.status==='IN_PROGRESS').length}</strong><small>В работе</small></div><div class="mobile-counter urgent"><strong>${active.filter(t=>['HIGH','EMERGENCY'].includes(t.priority)).length}</strong><small>Срочных</small></div>`;
  const search=(document.getElementById('mobile-search')?.value||'').trim().toLowerCase();
  const filter=document.getElementById('mobile-filter')?.value||'all';
  const visible=active.filter(t=>(!search||`${t.id} ${t.object_name} ${t.address} ${t.description}`.toLowerCase().includes(search))&&(filter==='all'||filter==='new'&&t.status==='ASSIGNED'||filter==='progress'&&['ACCEPTED','IN_PROGRESS','WAITING'].includes(t.status)||filter==='urgent'&&['HIGH','EMERGENCY'].includes(t.priority)));
  if(!visible.length){elements.list.innerHTML='<div class="mobile-empty"><strong>Всё спокойно</strong>Здесь появятся назначенные вам заявки.<br>Если включён фильтр, попробуйте изменить его.</div>';return;}
  elements.list.innerHTML='';
  visible.forEach(ticket=>{
    const wrapper=document.createElement('button');wrapper.type='button';
    wrapper.className=`mobile-ticket ${ticket.priority==='EMERGENCY'?'urgent':''}`;
    wrapper.innerHTML=`<div class="mobile-ticket-meta"><span>ЗАЯВКА № ${ticket.id}</span>${renderPriorityBadge(ticket.priority)}</div><h3>${escapeHtml(ticket.object_name || "Заявка")}</h3><div class="mobile-ticket-address">${escapeHtml(ticket.address || "Адрес не указан")}</div><p class="mobile-ticket-description">${escapeHtml(ticket.description || "—")}</p><footer class="mobile-ticket-footer"><span class="pill ${ticket.status==='WAITING'?'warn':''}">${escapeHtml(getStatusLabel(ticket.status))}</span><span>Открыть заявку <span class="mobile-ticket-arrow">↗</span></span></footer>`;
    wrapper.addEventListener('click',()=>openTicket(ticket.id));elements.list.appendChild(wrapper);
  });
}

function setActiveTab(tab) {
  const isHistory=tab==='history';
  elements.tabTickets?.classList.toggle('active',!isHistory);
  elements.tabHistory?.classList.toggle('active',isHistory);
  elements.ticketsPanel?.classList.toggle('hidden',isHistory);
  elements.historyPanel?.classList.toggle('hidden',!isHistory);
  elements.ticketDetailCard?.classList.add('hidden');
  elements.historyDetailCard?.classList.toggle('hidden',!isHistory);
  document.querySelector('.mobile-filterbar')?.classList.toggle('hidden',isHistory);
}

function updateHistoryIndicators() {
  if (elements.historyOffline) {
    elements.historyOffline.classList.toggle("hidden", !state.historyOffline);
  }
  if (elements.historyUpdated) {
    elements.historyUpdated.textContent = state.historyUpdatedAt
      ? `Обновлено: ${formatDate(state.historyUpdatedAt)}`
      : "—";
  }
}

function renderHistoryList() {
  if (!elements.historyList) return;
  if (!state.historyItems.length) {
    elements.historyList.innerHTML = `<div class="text-sm text-slate-500">История не найдена.</div>`;
    return;
  }
  elements.historyList.innerHTML = "";
  state.historyItems.forEach((item) => {
    const wrapper = document.createElement("button");
    wrapper.type = "button";
    wrapper.className =
      "w-full text-left border border-slate-200 rounded-xl p-3 hover:border-slate-400 transition bg-slate-50";
    wrapper.innerHTML = `
      <div class="flex items-start justify-between gap-2">
        <div>
          <div class="font-semibold">${escapeHtml(item.object_name || "Заявка")}</div>
          <div class="text-xs text-slate-500">${escapeHtml(item.address || "Адрес не указан")}</div>
        </div>
        <span class="text-xs font-semibold bg-slate-200 text-slate-700 px-2 py-1 rounded-full">${getStatusLabel(
          item.status
        )}</span>
      </div>
      <div class="mt-2 text-xs text-slate-500">Закрыта: ${formatDate(item.closed_at)}</div>
    `;
    wrapper.addEventListener("click", () => openHistoryTicket(item.ticket_id));
    elements.historyList.appendChild(wrapper);
  });
}

function renderHistoryDetail(timeline) {
  if (!elements.historyDetail) return;
  if (!timeline || !timeline.length) {
    elements.historyDetail.innerHTML = `<div class="text-sm text-slate-500">Событий нет.</div>`;
    return;
  }
  elements.historyDetail.innerHTML = timeline
    .map((event) => {
      if (event.type === "STATUS") {
        return `
          <div class="border border-slate-200 rounded-lg p-2">
            <div class="text-xs text-slate-500">${formatDate(event.created_at)} · ${
              event.actor === "me" ? "Вы" : "Другой"
            }</div>
            <div>Статус: ${getStatusLabel(event.status)}</div>
          </div>
        `;
      }
      if (event.type === "COMMENT") {
        return `
          <div class="border border-slate-200 rounded-lg p-2">
            <div class="text-xs text-slate-500">${formatDate(event.created_at)} · ${
              event.actor === "me" ? "Вы" : "Другой"
            }</div>
            <div>${escapeHtml(event.body || "—")}</div>
          </div>
        `;
      }
      if (event.type === "PHOTO") {
        const link = event.url ? `<a href="${escapeHtml(event.url)}" class="text-blue-600 underline">Открыть фото</a>` : "—";
        return `
          <div class="border border-slate-200 rounded-lg p-2">
            <div class="text-xs text-slate-500">${formatDate(event.created_at)} · ${
              event.actor === "me" ? "Вы" : "Другой"
            }</div>
            <div>${link}</div>
          </div>
        `;
      }
      return "";
    })
    .join("");
}

function buildSelect(id, options, selected) {
  const opts = options
    .map(
      (opt) =>
        `<option value="${opt}" ${opt === selected ? "selected" : ""}>${({EQUIPMENT_FAILURE:"Неисправность оборудования",PASSENGER_TRAPPED:"Освобождение пассажира",FALSE_CALL:"Ложный вызов",POWER_ISSUE:"Проблема питания",EXTERNAL_REASON:"Внешняя причина",OTHER:"Другое"})[opt] || escapeHtml(opt)}</option>`
    )
    .join("");
  return `<select id="${id}" class="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1 text-sm">${opts}</select>`;
}

function renderDetail(ticket) {
  if (!elements.detail) return;
  if (!ticket) {
    elements.detail.innerHTML = "Выберите заявку в списке.";
    delete elements.detail.dataset.ticketId;
    updateTicketStatusBadge(null);
    return;
  }
  const drafts={};
  if(elements.detail.dataset.ticketId===String(ticket.id)) {
    for(const id of ['comment-body','waiting-reason','done-reason','done-comment']) {
      const input=document.getElementById(id);if(input)drafts[id]=input.value;
    }
  }
  elements.detail.dataset.ticketId=String(ticket.id);
  updateTicketStatusBadge(ticket);
  const mapUrl = build2gisWebUrl(ticket);
  const mapButton = mapUrl
    ? `<button id="btn-2gis" class="mt-2 w-full px-3 py-2 rounded-xl bg-slate-100 ring-1 ring-slate-200 text-sm">Открыть в 2GIS</button>`
    : "";
  const comments = (ticket.comments || [])
    .map(
      (c) =>
        `<div class="border border-slate-200 rounded-lg p-2"><div class="text-xs text-slate-500">${formatDate(
          c.created_at
        )}</div><div>${escapeHtml(c.body)}</div></div>`
    )
    .join("");
  elements.detail.innerHTML = `
    <div class="mobile-detail-sync mobile-connection text-xs mb-4" role="status">${escapeHtml(elements.syncStatus.textContent)}</div>
    <div class="space-y-2">
      <div><span class="font-semibold">Объект:</span> ${escapeHtml(ticket.object_name || "—")}</div>
      <div><span class="font-semibold">Адрес:</span> ${escapeHtml(ticket.address || "—")}</div>
      <div><span class="font-semibold">Приоритет:</span> ${renderPriorityBadge(ticket.priority)}</div>
      ${mapButton}
      <div><span class="font-semibold">Описание:</span> ${escapeHtml(ticket.description || "—")}</div>
      ${ticket.waiting_reason?`<div><strong>Ожидание:</strong> ${escapeHtml(ticket.waiting_reason)}</div>`:''}
      ${ticket.close_comment?`<div><strong>Итог работы:</strong> ${escapeHtml(ticket.close_comment)}</div>`:''}
      <div class="text-xs text-slate-500">Назначено: ${ticket.assigned_at ? formatDate(ticket.assigned_at) : "—"}</div>
    </div>
    <div class="mt-4 space-y-3">
      <p class="text-xs muted">${({ASSIGNED:'Примите заявку, чтобы начать выезд.',ACCEPTED:'На объекте нажмите «В работу». Понадобится доступ к геолокации.',IN_PROGRESS:'После устранения неисправности укажите причину и завершите заявку.',WAITING:'Когда сможете продолжить, нажмите «В работу».',COMPLETED:'Работа завершена. Спасибо!',CANCELLED:'Заявка отменена.'})[ticket.status] || ''}</p>
      <div class="mobile-action-grid grid grid-cols-2 gap-2">
        <button id="btn-accept" class="px-3 py-2 rounded-xl bg-slate-900 text-white text-sm">Принять</button>
        <button id="btn-progress" class="px-3 py-2 rounded-xl bg-slate-900 text-white text-sm">В работу</button>
        <button id="btn-waiting" class="px-3 py-2 rounded-xl bg-slate-900 text-white text-sm">Ожидание</button>
        <button id="btn-done" class="px-3 py-2 rounded-xl bg-slate-900 text-white text-sm">Завершить</button>
      </div>
      <div>
        <label class="text-xs text-slate-500">Причина ожидания</label>
        <input id="waiting-reason" class="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1 text-sm" placeholder="Например: нет доступа" />
      </div>
      <div>
        <label class="text-xs text-slate-500">Комментарий</label>
        <textarea id="comment-body" class="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1 text-sm" rows="2" placeholder="Добавить комментарий"></textarea>
        <button id="btn-comment" class="mt-2 px-3 py-2 rounded-xl bg-slate-100 ring-1 ring-slate-200 text-sm">Добавить комментарий</button>
      </div>
      <div>
        <label class="text-xs text-slate-500">Причина закрытия</label>
        ${buildSelect("done-reason", CLOSE_REASONS, "OTHER")}
        <input id="done-comment" class="mt-2 w-full rounded-lg border border-slate-200 px-2 py-1 text-sm" placeholder="Комментарий к закрытию (опционально)" />
      </div>
      <div>
        <label class="text-xs text-slate-500">Фото</label>
        <label class="block secondary mt-2 cursor-pointer text-center" for="photo-input">Добавить фото<input id="photo-input" type="file" accept="image/*" capture="environment" class="sr-only" /></label>
        <div id="photo-queue" class="text-xs text-slate-500 mt-1">—</div>
        <div class="mt-2 space-y-2">${(ticket.attachments||[]).map(a=>`<a class="block text-link" target="_blank" rel="noopener" href="${escapeHtml(a.url)}">↗ ${escapeHtml(a.name||'Фото')}</a>`).join('')}</div>
      </div>
      <div>
        <div class="text-xs text-slate-500">Комментарии</div>
        <div class="space-y-2 mt-1">${comments || '<div class="text-xs text-slate-400">Комментариев нет.</div>'}</div>
      </div>
    </div>
  `;

  for(const [id,value] of Object.entries(drafts)){const input=document.getElementById(id);if(input)input.value=value;}

  for(const [id,visible] of [['waiting-reason',ticket.status==='IN_PROGRESS'],['done-reason',ticket.status==='IN_PROGRESS']]) {
    document.getElementById(id)?.parentElement.classList.toggle('hidden',!visible);
  }
  const liftHistory=document.createElement('details');liftHistory.className='mobile-lift-history';
  if(ticket.asset_id){liftHistory.innerHTML='<summary class="cursor-pointer font-semibold">История этого лифта</summary><div class="mt-3 text-xs muted" id="mobile-lift-history">Загружаем историю…</div>';elements.detail.appendChild(liftHistory);loadMobileLiftHistory(ticket);}
  const btnAccept = document.getElementById("btn-accept");
  const btnProgress = document.getElementById("btn-progress");
  const btnWaiting = document.getElementById("btn-waiting");
  const btnDone = document.getElementById("btn-done");
  const btnComment = document.getElementById("btn-comment");
  const btn2gis = document.getElementById("btn-2gis");
  const photoInput = document.getElementById("photo-input");
  const waitingReason = document.getElementById("waiting-reason");
  const commentBody = document.getElementById("comment-body");
  const doneReason = document.getElementById("done-reason");
  const doneComment = document.getElementById("done-comment");

  btnAccept.disabled = ticket.status !== "ASSIGNED";
  btnComment.disabled = ["COMPLETED","CANCELLED"].includes(ticket.status);
  photoInput.disabled = ["COMPLETED","CANCELLED"].includes(ticket.status);
  btnProgress.disabled = !["ACCEPTED", "WAITING"].includes(ticket.status);
  btnWaiting.disabled = ticket.status !== "IN_PROGRESS";
  btnDone.disabled = ticket.status !== "IN_PROGRESS";
  if(queueBusy)for(const button of [btnAccept,btnProgress,btnWaiting,btnDone,btnComment])button.disabled=true;

  btnAccept.addEventListener("click", () => {
    queueEvent(ticket, "TICKET_ACCEPT", {});
  });
  btnProgress.addEventListener("click", () => {
    if (ticket.status !== "ACCEPTED") {
      queueEvent(ticket, "TICKET_IN_PROGRESS", {});
      return;
    }
    if (!navigator.geolocation) {
      alert("Чтобы перевести принятую заявку в работу, разрешите геолокацию. Радиус объекта: 500 м.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coords = position.coords || {};
        queueEvent(ticket, "TICKET_IN_PROGRESS", {
          current_lat: coords.latitude,
          current_lng: coords.longitude,
        });
      },
      () => {
        alert("Чтобы перевести принятую заявку в работу, разрешите геолокацию. Радиус объекта: 500 м.");
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 }
    );
  });
  btnWaiting.addEventListener("click", () => {
    const reason = waitingReason.value.trim();
    queueEvent(ticket, "TICKET_WAITING", { waiting_reason: reason });
  });
  btnDone.addEventListener("click", () => {
    const reason = doneReason.value;
    const comment = doneComment.value.trim();
    queueEvent(ticket, "TICKET_DONE", { close_reason: reason, close_comment: comment });
  });
  btnComment.addEventListener("click", () => {
    const body = commentBody.value.trim();
    queueEvent(ticket, "TICKET_ADD_COMMENT", { body });
  });
  if (btn2gis && mapUrl) {
    btn2gis.addEventListener("click", () => {
      if (window.MOBILE_BOOTSTRAP?.debug2gis) {
        const debugLat = typeof parse2gisCoord === "function" ? parse2gisCoord(ticket.lat) : ticket.lat;
        const debugLon =
          typeof parse2gisCoord === "function"
            ? parse2gisCoord(ticket.lng ?? ticket.lon)
            : ticket.lng ?? ticket.lon;
        console.info("2GIS coords", { ticketId: ticket.id, lat: debugLat, lng: debugLon });
        console.info("2GIS url", mapUrl);
      }
      window.location.assign(mapUrl);
    });
  }
  photoInput.addEventListener("change", async () => {
    const file = photoInput.files?.[0];
    if (!file) return;
    if (file.size > MAX_PHOTO_SIZE_BYTES) {
      alert(`Фото слишком большое. Максимум: ${formatFileSize(MAX_PHOTO_SIZE_BYTES)}.`);
      photoInput.value = "";
      return;
    }
    const queuedPhotos = await listOutboxPhotos();
    if (queuedPhotos.length >= MAX_QUEUED_PHOTOS) {
      alert(`В очереди уже ${MAX_QUEUED_PHOTOS} фото. Синхронизируйте или удалите ошибочные фото.`);
      photoInput.value = "";
      return;
    }
    const photo = {
      id: uid(),
      ticket_id: ticket.id,
      name: file.name,
      type: file.type,
      size: file.size,
      blob: file,
      created_at: new Date().toISOString(),
      status: "pending",
    };
    await putOutboxPhoto(photo);
    photoInput.value = "";
    await renderPhotoQueue(ticket.id);
    await syncAll();
  });
  renderPhotoQueue(ticket.id);
}

async function renderPhotoQueue(ticketId) {
  const queue = document.getElementById("photo-queue");
  if (!queue) return;
  const photos = await listOutboxPhotos();
  const ticketPhotos = photos.filter((p) => p.ticket_id === ticketId);
  const pending = ticketPhotos.filter((p) => p.status === "pending").length;
  const failed = ticketPhotos.filter((p) => p.status === "error").length;
  if (failed) {
    queue.textContent = `Фото: ожидают ${pending}, ошибка ${failed}. Проверьте блок "Требует внимания".`;
  } else if (pending) {
    queue.textContent = `Фото в очереди: ${pending}`;
  } else {
    queue.textContent = "Фото не ожидают загрузки.";
  }
}

async function openTicket(id) {
  state.selectedId = id;
  elements.ticketDetailCard?.classList.remove('hidden');
  let ticket = null;
  const queued=(await listOutboxEvents()).some(e=>e.ticket_id===id);
  if (state.online && !queued) {
    try {
      const res = await mobileFetch(`/api/tickets/${id}`);
      if([403,404].includes(res.status)){elements.ticketDetailCard?.classList.add('hidden');await withStore('tickets_cache','readwrite',store=>store.delete(id));return;}
      if (res.ok) {
        ticket = await res.json();
        await saveTicketCache(ticket);
      }
    } catch (err) {
      ticket = null;
    }
  }
  if (!ticket) {
    ticket = await loadTicketCache(id);
  }
  renderDetail(ticket);
}

async function openHistoryTicket(ticketId) {
  state.historySelectedId = ticketId;
  const selected = state.historyItems.find((item) => item.ticket_id === ticketId);
  if (elements.historyDetailStatus) {
    elements.historyDetailStatus.textContent = selected
      ? `${getStatusLabel(selected.status)} · ${formatDate(selected.closed_at)}`
      : "—";
  }
  let timeline = null;
  let usedCache = false;
  if (state.online) {
    try {
      const res = await mobileFetch(`/api/me/tickets/${ticketId}/timeline`);
      if (res.ok) {
        timeline = await res.json();
        await saveHistoryTimelineCache(ticketId, timeline || []);
        state.historyUpdatedAt = new Date().toISOString();
      }
    } catch (err) {
      timeline = null;
    }
  }
  if (!timeline) {
    const cached = await loadHistoryTimelineCache(ticketId);
    timeline = cached?.items || [];
    usedCache = true;
    if (!state.historyUpdatedAt && cached?.updated_at) {
      state.historyUpdatedAt = cached.updated_at;
    }
  }
  state.historyOffline = !state.online || usedCache;
  updateHistoryIndicators();
  renderHistoryDetail(timeline);
}

async function refreshTickets() {
  if (!elements.list) return;
  if (state.online) {
    try {
      const res = await mobileFetch("/api/me/tickets");
      if (res.ok) {
        const data = await res.json();
        const queuedIds=new Set((await listOutboxEvents()).map(e=>e.ticket_id));
        state.tickets=[];
        for(const t of data||[]) {
          const cached=queuedIds.has(t.id)?await loadTicketCache(t.id):null;
          const item=cached||t;
          state.tickets.push(item);await saveTicketCache(item);
        }
        await saveListCache(state.tickets);
      }
    } catch (err) {
      state.tickets = await loadListCache();
    }
  } else {
    state.tickets = await loadListCache();
  }
  renderList();
}

async function refreshHistoryList() {
  const filters = {
    date_from: elements.historyDateFrom?.value || "",
    date_to: elements.historyDateTo?.value || "",
  };
  let items = [];
  let usedCache = false;
  let fetchOk = false;
  if (state.online) {
    try {
      const params = new URLSearchParams();
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to) params.set("date_to", filters.date_to);
      const res = await mobileFetch(`/api/me/history?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        items = data.items || [];
        await saveHistoryListCache(items, filters);
        state.historyUpdatedAt = new Date().toISOString();
        fetchOk = true;
      }
    } catch (err) {
      items = [];
    }
  }
  if (!fetchOk) {
    const cached = await loadHistoryListCache();
    if (cached?.items) {
      items = cached.items;
      usedCache = true;
      if (cached.filters) {
        if (elements.historyDateFrom && !filters.date_from) {
          elements.historyDateFrom.value = cached.filters.date_from || "";
        }
        if (elements.historyDateTo && !filters.date_to) {
          elements.historyDateTo.value = cached.filters.date_to || "";
        }
      }
      if (cached.updated_at) {
        state.historyUpdatedAt = cached.updated_at;
      }
    }
  }
  state.historyItems = items;
  state.historyOffline = !state.online || usedCache;
  renderHistoryList();
  updateHistoryIndicators();
  if (state.historyItems.length) {
    await openHistoryTicket(state.historyItems[0].ticket_id);
  } else {
    renderHistoryDetail([]);
  }
}

async function queueEvent(ticket, type, payload) {
  if(queueBusy)return;
  queueBusy=true;
  try {
    const latest=await loadTicketCache(ticket.id)||ticket;
    const valid={TICKET_ACCEPT:['ASSIGNED'],TICKET_IN_PROGRESS:['ACCEPTED','WAITING'],TICKET_WAITING:['IN_PROGRESS'],TICKET_DONE:['IN_PROGRESS']};
    if(valid[type]&&!valid[type].includes(latest.status))return;
    await performQueueEvent(latest,type,payload);
  } finally {
    queueBusy=false;
    if(state.selectedId===ticket.id)renderDetail(await loadTicketCache(ticket.id)||ticket);
  }
}

async function performQueueEvent(ticket, type, payload) {
  if (!ticket) return;
  const expectedVersion = ticket.version || 1;
  const event = {
    id: uid(),
    type,
    ticket_id: ticket.id,
    expected_version: expectedVersion,
    created_at: new Date().toISOString(),
    payload: payload || {},
    status: "pending",
  };
  if (type === "TICKET_WAITING" && !(payload?.waiting_reason || "").trim()) {
    alert("Укажите причину ожидания.");
    return;
  }
  if (type === "TICKET_ADD_COMMENT" && !(payload?.body || "").trim()) {
    alert("Комментарий не может быть пустым.");
    return;
  }
  if (type === "TICKET_DONE" && !(payload?.close_reason || "").trim()) {
    alert("Укажите причину закрытия.");
    return;
  }
  await putOutboxEvent(event);
  if(type==='TICKET_ADD_COMMENT'&&document.getElementById('comment-body'))document.getElementById('comment-body').value='';
  const updated = { ...ticket };
  if (type === "TICKET_ACCEPT") {
    updated.status = "ACCEPTED";
    updated.accepted_at = new Date().toISOString();
  }
  if (type === "TICKET_IN_PROGRESS") {
    updated.status = "IN_PROGRESS";
    updated.arrived_at = new Date().toISOString();
    updated.waiting_at = null;
    updated.waiting_reason = null;
  }
  if (type === "TICKET_WAITING") {
    updated.status = "WAITING";
    updated.waiting_at = new Date().toISOString();
    updated.waiting_reason = payload.waiting_reason;
  }
  if (type === "TICKET_DONE") {
    updated.status = "COMPLETED";
    updated.completed_at = new Date().toISOString();
    updated.close_reason = payload.close_reason;
    updated.close_comment = payload.close_comment || "";
  }
  if (type === "TICKET_ADD_COMMENT") {
    updated.comments = [
      { id: `local_${event.id}`, body: payload.body, created_at: new Date().toISOString(), user_id: null },
      ...(updated.comments || []),
    ];
  }
  updated.version = expectedVersion + 1;
  await saveTicketCache(updated);
  state.tickets = state.tickets.map((t) => (t.id === updated.id ? { ...t, ...updated } : t));
  await saveListCache(state.tickets);
  renderList();
  renderDetail(updated);
  await updateSyncIndicators();
  await syncAll();
}

async function syncEvents() {
  const events = await listOutboxEvents();
  const pending = events.filter((e) => e.status === "pending");
  if (!pending.length || !state.online) return;
  pending.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
  const payload = { events: pending.map(({ status, error, ...evt }) => evt) };
  let res;
  try {
    res = await mobileFetch("/api/sync/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    return;
  }
  if (!res.ok) {
    return;
  }
  const data = await res.json();
  for (const result of data.results || []) {
    const local = pending.find((e) => e.id === result.id);
    if (!local) continue;
    if (result.ok) {
      await deleteOutboxEvent(local.id);
      if (result.ticket?.id) {
        const cached = await loadTicketCache(result.ticket.id);
        const merged = { ...(cached || {}), ...result.ticket };
        await saveTicketCache(merged);
        state.tickets = state.tickets.map((t) => (t.id === merged.id ? { ...t, ...merged } : t));
      }
    } else {
      local.status = "error";
      local.error = { code: result.code, message: result.message };
      await putOutboxEvent(local);
      if (result.code === "OUT_OF_RANGE") {
        const distance = Number.isFinite(result.distance_m) ? result.distance_m : "—";
        alert(`Вы слишком далеко от объекта. Нужно не дальше 500 м. Сейчас: ${distance} м`);
      }
      if (result.code === "NO_TARGET_COORDS") {
        alert("У заявки нет координат объекта. Перевести ее в работу нельзя.");
      }
      if (result.code === "NO_TECH_COORDS") {
        alert("Не удалось получить геолокацию. Разрешите доступ и попробуйте снова.");
      }
      if (result.code === "CONFLICT" && result.server_version && state.online) {
        await openTicket(local.ticket_id);
      }
    }
  }
  state.lastSync = new Date().toISOString();
  await updateSyncIndicators();
  renderList();
  await saveListCache(state.tickets);
  if (state.selectedId) {
    const refreshed = await loadTicketCache(state.selectedId);
    renderDetail(refreshed);
  }
}

async function syncPhotos() {
  if (!state.online) return;
  const photos = await listOutboxPhotos();
  for (const photo of photos.filter((p) => p.status === "pending")) {
    const formData = new FormData();
    formData.append("file", photo.blob, photo.name);
    formData.append("upload_id", photo.id);
    try {
      const res = await mobileFetch(`/api/tickets/${photo.ticket_id}/upload`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        await deleteOutboxPhoto(photo.id);
        if (state.selectedId === photo.ticket_id) {
          await openTicket(photo.ticket_id);
        }
      } else {
        let message = "Не удалось загрузить фото";
        try {
          const data = await res.json();
          message = data?.error?.message || data?.error || message;
          if (typeof message !== "string") {
            message = "Не удалось загрузить фото";
          }
        } catch (err) {
          message = `${message} (${res.status})`;
        }
        photo.status = "error";
        photo.error = { code: `UPLOAD_${res.status}`, message };
        await putOutboxPhoto(photo);
      }
    } catch (err) {
      // Transient network failures stay pending and retryable on the next sync.
    }
  }
}

async function syncAll() {
  if(syncPromise)return syncPromise;
  syncPromise=(async()=>{
    if(!state.online&&navigator.onLine)state.online=true;
    if(!state.online){await updateSyncIndicators();return;}
    if(!await verifyIdentity())return;
    if(!state.online){await updateSyncIndicators();return;}
    try{
      await syncEvents();await syncPhotos();await refreshTickets();
      if(state.selectedId){await renderPhotoQueue(state.selectedId);}
      if(state.online)state.lastSync=new Date().toISOString();
      await updateSyncIndicators();
    }catch(err){await updateSyncIndicators();}
  })();
  try{return await syncPromise;}finally{syncPromise=null;}
}

async function loadMobileLiftHistory(ticket) {
  let entry=await withStore('history_timeline_cache','readonly',store=>store.get(`lift-${ticket.asset_id}`));
  if(state.online){try{const res=await mobileFetch(`/api/me/lifts/${ticket.asset_id}/history`);if(res.ok){const data=await res.json();entry={id:`lift-${ticket.asset_id}`,items:data.items,updated_at:new Date().toISOString()};await withStore('history_timeline_cache','readwrite',store=>store.put(entry));}else if(res.status===403){entry=null;await withStore('history_timeline_cache','readwrite',store=>store.delete(`lift-${ticket.asset_id}`));}}catch(_){}}
  if(state.selectedId!==ticket.id)return;
  const el=document.getElementById('mobile-lift-history');if(!el)return;
  const items=(entry?.items||[]).filter(t=>t.id!==ticket.id);
  el.innerHTML=items.length?`<p class="mb-2">${state.online?'Обновлено':'Сохранено'} ${formatDate(entry.updated_at)}</p>`+items.map(t=>`<div class="border-t py-3"><div class="font-semibold">№ ${t.id} · ${escapeHtml(getStatusLabel(t.status))}</div><p class="mt-1">${escapeHtml(t.description||'Без описания')}</p>${t.close_comment?`<p class="mt-1">Итог: ${escapeHtml(t.close_comment)}</p>`:''}</div>`).join(''):'История пока не сохранена или предыдущих заявок нет.';
}

async function resetOffline() {
  const events = await listOutboxEvents();
  const photos = await listOutboxPhotos();
  const queuedCount = events.length + photos.length;
  const message = queuedCount
    ? `Сбросить офлайн-данные и удалить ${queuedCount} несинхронизированных действий/фото?`
    : "Сбросить локальный кэш приложения мастера?";
  if (!window.confirm(message)) return;
  await withStore("tickets_list_cache", "readwrite", (store) => store.clear());
  await withStore("tickets_cache", "readwrite", (store) => store.clear());
  await withStore("history_list_cache", "readwrite", (store) => store.clear());
  await withStore("history_timeline_cache", "readwrite", (store) => store.clear());
  await withStore("outbox_events", "readwrite", (store) => store.clear());
  await withStore("outbox_photos", "readwrite", (store) => store.clear());
  window.location.reload();
}

async function init() {
  if (window.MOBILE_BOOTSTRAP?.notTechnician) return;
  if(!mobileIdentity?.id){lockMobile();return;}
  if(!window.MOBILE_BOOTSTRAP?.offlineShell) localStorage.setItem('liftcrm-mobile-identity',JSON.stringify(mobileIdentity));
  document.getElementById('mobile-user-label').textContent=mobileIdentity.username;
  if(state.online&&!await verifyIdentity())return;
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistrations().then(regs=>regs.filter(r=>new URL(r.scope).pathname==='/static/').forEach(r=>r.unregister()));
    navigator.serviceWorker.register("/sw.js",{scope:'/'}).catch(() => {});
  }
  setActiveTab("tickets");
  await refreshTickets();
  await updateSyncIndicators();
  const deepTicket=Number(new URLSearchParams(location.search).get('ticket'));
  if(deepTicket&&state.tickets.some(t=>t.id===deepTicket))await openTicket(deepTicket);
  await syncAll();
  window.addEventListener("online", async () => {
    state.online = true;
    await syncAll();
    await refreshHistoryList();
  });
  window.addEventListener("offline", async () => {
    state.online = false;
    await updateSyncIndicators();
    state.historyOffline = true;
    updateHistoryIndicators();
  });
  // Online events can be missed after an offline reload or a temporary server outage.
  setInterval(()=>{if(document.visibilityState==='visible'&&navigator.onLine&&!state.authBlocked)syncAll();},30000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&navigator.onLine&&!state.authBlocked)syncAll();});
  elements.tabTickets?.addEventListener("click", () => setActiveTab("tickets"));
  elements.tabHistory?.addEventListener("click", async () => {
    setActiveTab("history");
    await refreshHistoryList();
  });
  elements.historyApply?.addEventListener("click", refreshHistoryList);
  elements.btnSync?.addEventListener("click", () => {state.online=navigator.onLine;return syncAll();});
  elements.btnReset?.addEventListener("click", resetOffline);
  document.getElementById('mobile-search')?.addEventListener('input',renderList);
  document.getElementById('mobile-filter')?.addEventListener('change',renderList);
  document.getElementById('mobile-back')?.addEventListener('click',()=>{state.selectedId=null;elements.ticketDetailCard?.classList.add('hidden');});
  for(const id of ['open-settings','tab-settings'])document.getElementById(id)?.addEventListener('click',()=>document.getElementById('mobile-settings').showModal());
  document.getElementById('close-settings')?.addEventListener('click',()=>document.getElementById('mobile-settings').close());
  document.getElementById('mobile-logout')?.addEventListener('click',async()=>{
    const count=(await listOutboxEvents()).length+(await listOutboxPhotos()).length;
    if(count&&!confirm(`В очереди ${count} действий. Они сохранятся для следующего входа в этот аккаунт. Выйти?`))return;
    if(!state.online){alert('Для выхода подключитесь к интернету.');return;}
    await mobileFetch('/api/logout',{method:'POST'});localStorage.removeItem('liftcrm-mobile-identity');location.href='/login';
  });
  let installPrompt=null;
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;document.getElementById('btn-install').classList.remove('hidden');});
  document.getElementById('btn-install')?.addEventListener('click',async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;document.getElementById('btn-install').classList.add('hidden');}});
  elements.outboxRetryAll?.addEventListener("click", retryAllFailedOutbox);
}

init().catch(err=>{
  if(elements.list)elements.list.innerHTML='<div class="mobile-empty"><strong>Не удалось открыть приложение</strong>Проверьте доступ к хранилищу браузера и перезагрузите страницу.</div>';
  console.error('Mobile initialization failed',err);
});

const DB_NAME = "liftcrm-mobile";
const DB_VERSION = 1;
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

const state = {
  tickets: [],
  selectedId: null,
  online: navigator.onLine,
  pendingCount: 0,
  errorCount: 0,
  lastSync: null,
};

const elements = {
  list: document.getElementById("tickets-list"),
  detail: document.getElementById("ticket-detail"),
  syncStatus: document.getElementById("sync-status"),
  lastSync: document.getElementById("last-sync"),
  ticketStatus: document.getElementById("ticket-status"),
  btnSync: document.getElementById("btn-sync"),
  btnReset: document.getElementById("btn-reset"),
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

function uid() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  return `evt_${Date.now()}_${Math.random().toString(16).slice(2)}`;
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
    tx.oncomplete = () => resolve(requestResult);
    tx.onerror = () => reject(tx.error);
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

async function updateSyncIndicators() {
  const events = await listOutboxEvents();
  state.pendingCount = events.filter((e) => e.status === "pending").length;
  state.errorCount = events.filter((e) => e.status === "error").length;
  const online = state.online;
  let text = "—";
  if (!online) {
    text = state.pendingCount > 0 ? `Оффлайн • В очереди ${state.pendingCount}` : "Оффлайн";
  } else if (state.errorCount > 0) {
    text = `Ошибка (${state.errorCount})`;
  } else if (state.pendingCount > 0) {
    text = `В очереди ${state.pendingCount}`;
  } else {
    text = "Синхронизировано";
  }
  elements.syncStatus.textContent = text;
  elements.lastSync.textContent = state.lastSync ? `Последняя синхронизация: ${formatDate(state.lastSync)}` : "—";
}

function updateTicketStatusBadge(ticket) {
  if (!elements.ticketStatus) return;
  if (!ticket) {
    elements.ticketStatus.textContent = "—";
    return;
  }
  elements.ticketStatus.textContent = `Статус: ${getStatusLabel(ticket.status)} · v${ticket.version || 1}`;
}

function renderList() {
  if (!elements.list) return;
  if (!state.tickets.length) {
    elements.list.innerHTML = `<div class="text-sm text-slate-500">Заявки не найдены.</div>`;
    return;
  }
  elements.list.innerHTML = "";
  state.tickets.forEach((ticket) => {
    const wrapper = document.createElement("button");
    wrapper.type = "button";
    wrapper.className =
      "w-full text-left border border-slate-200 rounded-xl p-3 hover:border-slate-400 transition bg-slate-50";
    wrapper.innerHTML = `
      <div class="flex items-start justify-between gap-2">
        <div>
          <div class="font-semibold">${ticket.object_name || "Заявка"}</div>
          <div class="text-xs text-slate-500">${ticket.address || "Адрес не указан"}</div>
        </div>
        <span class="text-xs font-semibold bg-slate-200 text-slate-700 px-2 py-1 rounded-full">${getStatusLabel(ticket.status)}</span>
      </div>
      <div class="mt-2 text-xs text-slate-500">Обновлено: ${formatDate(ticket.updated_at)}</div>
    `;
    wrapper.addEventListener("click", () => openTicket(ticket.id));
    elements.list.appendChild(wrapper);
  });
}

function buildSelect(id, options, selected) {
  const opts = options
    .map(
      (opt) =>
        `<option value="${opt}" ${opt === selected ? "selected" : ""}>${opt}</option>`
    )
    .join("");
  return `<select id="${id}" class="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1 text-sm">${opts}</select>`;
}

function renderDetail(ticket) {
  if (!elements.detail) return;
  if (!ticket) {
    elements.detail.innerHTML = "Выберите заявку в списке.";
    updateTicketStatusBadge(null);
    return;
  }
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
        )}</div><div>${c.body}</div></div>`
    )
    .join("");
  elements.detail.innerHTML = `
    <div class="space-y-2">
      <div><span class="font-semibold">Объект:</span> ${ticket.object_name || "—"}</div>
      <div><span class="font-semibold">Адрес:</span> ${ticket.address || "—"}</div>
      ${mapButton}
      <div><span class="font-semibold">Описание:</span> ${ticket.description || "—"}</div>
      <div class="text-xs text-slate-500">Назначено: ${ticket.assigned_at ? formatDate(ticket.assigned_at) : "—"}</div>
    </div>
    <div class="mt-4 space-y-3">
      <div class="grid grid-cols-2 gap-2">
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
        <input id="photo-input" type="file" accept="image/*" capture="environment" class="mt-1 block w-full text-sm" />
        <div id="photo-queue" class="text-xs text-slate-500 mt-1">—</div>
      </div>
      <div>
        <div class="text-xs text-slate-500">Комментарии</div>
        <div class="space-y-2 mt-1">${comments || '<div class="text-xs text-slate-400">Комментариев нет.</div>'}</div>
      </div>
    </div>
  `;

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
  btnProgress.disabled = !["ACCEPTED", "WAITING"].includes(ticket.status);
  btnWaiting.disabled = ticket.status !== "IN_PROGRESS";
  btnDone.disabled = ticket.status !== "IN_PROGRESS";

  btnAccept.addEventListener("click", () => {
    if (!navigator.geolocation) {
      alert("Нужно разрешить геолокацию, чтобы принять заявку (радиус 500м).");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coords = position.coords || {};
        queueEvent(ticket, "TICKET_ACCEPT", {
          current_lat: coords.latitude,
          current_lng: coords.longitude,
        });
      },
      () => {
        alert("Нужно разрешить геолокацию, чтобы принять заявку (радиус 500м).");
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 }
    );
  });
  btnProgress.addEventListener("click", () => queueEvent(ticket, "TICKET_IN_PROGRESS", {}));
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
    const photo = {
      id: uid(),
      ticket_id: ticket.id,
      name: file.name,
      type: file.type,
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
  const count = photos.filter((p) => p.ticket_id === ticketId).length;
  queue.textContent = count ? `Фото в очереди: ${count}` : "Фото не ожидают загрузки.";
}

async function openTicket(id) {
  state.selectedId = id;
  let ticket = null;
  if (state.online) {
    try {
      const res = await fetch(`/api/tickets/${id}`);
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

async function refreshTickets() {
  if (!elements.list) return;
  if (state.online) {
    try {
      const res = await fetch("/api/me/tickets");
      if (res.ok) {
        const data = await res.json();
        state.tickets = data || [];
        await saveListCache(state.tickets);
        for (const t of state.tickets) {
          await saveTicketCache(t);
        }
      }
    } catch (err) {
      state.tickets = await loadListCache();
    }
  } else {
    state.tickets = await loadListCache();
  }
  renderList();
}

async function queueEvent(ticket, type, payload) {
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
  const res = await fetch("/api/sync/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
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
        alert(`Вы слишком далеко. Нужно быть в радиусе 500м. Сейчас: ${distance}м`);
      }
      if (result.code === "NO_TARGET_COORDS") {
        alert("У заявки нет координат объекта. Принять нельзя.");
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
    try {
      const res = await fetch(`/api/tickets/${photo.ticket_id}/upload`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        await deleteOutboxPhoto(photo.id);
        if (state.selectedId === photo.ticket_id) {
          await openTicket(photo.ticket_id);
        }
      }
    } catch (err) {
      // keep queued
    }
  }
}

async function syncAll() {
  if (!state.online) {
    await updateSyncIndicators();
    return;
  }
  await syncEvents();
  await syncPhotos();
  await updateSyncIndicators();
}

async function resetOffline() {
  await withStore("tickets_list_cache", "readwrite", (store) => store.clear());
  await withStore("tickets_cache", "readwrite", (store) => store.clear());
  await withStore("outbox_events", "readwrite", (store) => store.clear());
  await withStore("outbox_photos", "readwrite", (store) => store.clear());
  window.location.reload();
}

async function init() {
  if (window.MOBILE_BOOTSTRAP?.notTechnician) return;
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  }
  await refreshTickets();
  await updateSyncIndicators();
  if (state.tickets.length) {
    await openTicket(state.tickets[0].id);
  }
  await syncAll();
  window.addEventListener("online", async () => {
    state.online = true;
    await refreshTickets();
    await syncAll();
  });
  window.addEventListener("offline", async () => {
    state.online = false;
    await updateSyncIndicators();
  });
  elements.btnSync?.addEventListener("click", syncAll);
  elements.btnReset?.addEventListener("click", resetOffline);
}

init();

(() => {
  const liftId = document.querySelector("[data-lift-id]")?.getAttribute("data-lift-id");
  const headerEl = document.getElementById("lift-header");
  const listEl = document.getElementById("history-items");
  const stateEl = document.getElementById("history-state");
  const formEl = document.getElementById("history-filters");
  const inputFrom = document.getElementById("history-from");
  const inputTo = document.getElementById("history-to");
  const inputQ = document.getElementById("history-q");
  const tabButtons = document.querySelectorAll("[data-tab]");
  const tabContents = document.querySelectorAll("[data-tab-content]");
  let openTicketId = null;

  if (!liftId) return;

  function setActiveTab(tab) {
    tabButtons.forEach((btn) => {
      if (btn.dataset.tab === tab) {
        btn.classList.add("bg-slate-100");
      } else {
        btn.classList.remove("bg-slate-100");
      }
    });
    tabContents.forEach((section) => {
      section.classList.toggle("hidden", section.dataset.tabContent !== tab);
    });
    if (tab === "history") {
      window.location.hash = "history";
    } else if (tab === "info") {
      window.location.hash = "info";
    }
  }

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
  });

  const initialTab = window.location.hash.replace("#", "") || "info";
  setActiveTab(initialTab === "info" ? "info" : "history");

  function formatDateTime(ts) {
    if (!ts) return "—";
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) return ts;
    return date.toLocaleString("ru-RU");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatMinutes(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    const minutes = Math.round(seconds / 60);
    return `${minutes} мин`;
  }

  function statusBadge(status) {
    const map = {
      NEW: { label: "Новая", cls: "bg-slate-100 text-slate-700" },
      ASSIGNED: { label: "Назначена", cls: "bg-sky-100 text-sky-700" },
      ACCEPTED: { label: "Принята", cls: "bg-amber-100 text-amber-700" },
      IN_PROGRESS: { label: "В работе", cls: "bg-blue-100 text-blue-700" },
      WAITING: { label: "Ожидание", cls: "bg-orange-100 text-orange-700" },
      COMPLETED: { label: "Завершена", cls: "bg-emerald-100 text-emerald-700" },
      CANCELLED: { label: "Отменена", cls: "bg-rose-100 text-rose-700" },
    };
    return map[status] || { label: status || "—", cls: "bg-slate-100 text-slate-700" };
  }

  function eventKindLabel(kind) {
    switch (kind) {
      case "CREATE":
        return "Создание";
      case "ASSIGN":
        return "Назначение";
      case "STATUS_CHANGE":
        return "Статус";
      case "WAITING":
        return "Ожидание";
      case "CLOSE":
        return "Закрытие";
      case "COMMENT":
        return "Комментарий";
      case "ATTACHMENT":
        return "Вложение";
      default:
        return kind || "Событие";
    }
  }

  function ticketTitle(ticket) {
    if (ticket.title && ticket.title.trim()) return ticket.title.trim();
    if (ticket.description && ticket.description.trim()) {
      const short = ticket.description.trim();
      return short.length > 60 ? `${short.slice(0, 60)}…` : short;
    }
    return `Заявка #${ticket.id}`;
  }

  function setHeader(lift) {
    if (!lift) {
      headerEl.innerHTML = '<div class="text-slate-500">Данные лифта не найдены.</div>';
      return;
    }
    headerEl.innerHTML = `
      <div class="text-slate-700 font-semibold text-lg">${escapeHtml(lift.lift_label || "Лифт без метки")}</div>
      <div class="text-slate-500">Серийный номер: <span class="text-slate-700">${escapeHtml(lift.serial_no || "—")}</span></div>
      <div class="text-slate-500">Адрес: <span class="text-slate-700">${escapeHtml(lift.address || "—")}</span></div>
      <div class="text-slate-500">Подъезд: <span class="text-slate-700">${escapeHtml(lift.entrance || "—")}</span></div>
      <div class="text-slate-500">Статус: <span class="text-slate-700">${escapeHtml(lift.status || "—")}</span></div>
    `;
  }

  function renderEvents(events) {
    if (!events.length) {
      return '<div class="text-sm text-slate-500">Нет событий по заявке.</div>';
    }
    return events
      .map((event) => {
        const actor = event.actor ? `${event.actor.username} (${event.actor.role})` : "—";
        return `
          <div class="flex flex-col gap-1 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <span>${eventKindLabel(event.kind)}</span>
              <span>${formatDateTime(event.ts)}</span>
            </div>
            <div class="text-sm text-slate-700">${escapeHtml(event.text || "—")}</div>
            <div class="text-xs text-slate-500">Исполнитель: <span class="text-slate-700">${escapeHtml(actor)}</span></div>
          </div>
        `;
      })
      .join("");
  }

  function renderTickets(tickets) {
    if (!tickets.length) {
      listEl.innerHTML = '<div class="text-sm text-slate-500">За выбранный период заявок не найдено.</div>';
      return;
    }
    listEl.innerHTML = tickets
      .map((item) => {
        const { ticket, summary, events } = item;
        const badge = statusBadge(ticket.status);
        const assigned = ticket.assigned?.username || ticket.assigned?.name;
        const ticketLink = `/admin?ui=admin&ticket_id=${ticket.id}`;
        return `
          <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="space-y-1">
                <div class="text-base font-semibold text-slate-800">#${ticket.id} — ${escapeHtml(ticketTitle(ticket))}</div>
                <div class="text-xs text-slate-500">
                  Открыта: <span class="text-slate-700">${formatDateTime(ticket.created_at)}</span>
                  ${ticket.completed_at ? ` · Закрыта: <span class="text-slate-700">${formatDateTime(ticket.completed_at)}</span>` : ""}
                </div>
                <div class="text-xs text-slate-500">
                  Мастер: <span class="text-slate-700">${escapeHtml(assigned || "—")}</span>
                </div>
                <div class="text-xs text-slate-500">
                  Реакция: <span class="text-slate-700">${formatMinutes(summary.metrics.response_seconds)}</span>
                  · Ремонт: <span class="text-slate-700">${formatMinutes(summary.metrics.repair_seconds)}</span>
                  · Простой: <span class="text-slate-700">${formatMinutes(summary.metrics.downtime_seconds)}</span>
                </div>
              </div>
              <span class="px-2 py-1 rounded-lg text-xs font-semibold ${badge.cls}">${badge.label}</span>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <button data-ticket-toggle data-ticket-id="${ticket.id}" class="px-3 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold">Подробнее</button>
              <a href="${ticketLink}" class="px-3 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold ring-1 ring-slate-200">Открыть заявку</a>
            </div>
            <div data-ticket-details data-ticket-id="${ticket.id}" class="mt-4 space-y-3 hidden">
              ${renderEvents(events)}
            </div>
          </article>
        `;
      })
      .join("");

    if (openTicketId === null && tickets.length) {
      openTicketId = String(tickets[0].ticket.id);
    }
    updateDetails();
  }

  function updateDetails() {
    document.querySelectorAll("[data-ticket-details]").forEach((el) => {
      const isOpen = openTicketId === el.dataset.ticketId;
      el.classList.toggle("hidden", !isOpen);
    });
    document.querySelectorAll("[data-ticket-toggle]").forEach((btn) => {
      btn.textContent = openTicketId === btn.dataset.ticketId ? "Свернуть" : "Подробнее";
    });
    document.querySelectorAll("[data-ticket-toggle]").forEach((btn) => {
      btn.onclick = () => {
        const id = btn.dataset.ticketId;
        openTicketId = openTicketId === id ? null : id;
        updateDetails();
      };
    });
  }

  function applyFilterValuesFromQuery() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("from")) inputFrom.value = params.get("from");
    if (params.get("to")) inputTo.value = params.get("to");
    if (params.get("q")) inputQ.value = params.get("q");
  }

  async function loadHistory() {
    stateEl.textContent = "Загружаем историю...";
    try {
      const res = await fetch(`/api/lifts/${liftId}/history${window.location.search}`, { cache: "no-store" });
      if (!res.ok) {
        stateEl.textContent = "Не удалось загрузить историю.";
        listEl.innerHTML = "";
        return;
      }
      const data = await res.json();
      setHeader(data.lift);
      renderTickets(Array.isArray(data.tickets) ? data.tickets : []);
      stateEl.textContent = "";
    } catch (err) {
      stateEl.textContent = "Ошибка загрузки истории.";
      listEl.innerHTML = "";
    }
  }

  if (formEl) {
    formEl.addEventListener("submit", (event) => {
      event.preventDefault();
      const params = new URLSearchParams();
      if (inputFrom.value) params.set("from", inputFrom.value);
      if (inputTo.value) params.set("to", inputTo.value);
      if (inputQ.value) params.set("q", inputQ.value.trim());
      const qs = params.toString();
      window.location.search = qs ? `?${qs}` : "";
    });
  }

  applyFilterValuesFromQuery();
  loadHistory();
})();

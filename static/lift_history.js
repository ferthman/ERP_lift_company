(() => {
  const assetId = document.querySelector("[data-asset-id]")?.getAttribute("data-asset-id");
  const headerEl = document.getElementById("lift-header");
  const listEl = document.getElementById("history-items");
  const stateEl = document.getElementById("history-state");
  const formEl = document.getElementById("history-filters");
  const inputFrom = document.getElementById("history-from");
  const inputTo = document.getElementById("history-to");
  const inputQ = document.getElementById("history-q");

  if (!assetId) return;

  function formatDateTime(ts) {
    if (!ts) return "—";
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) return ts;
    return date.toLocaleString("ru-RU");
  }

  function kindLabel(kind) {
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

  function setHeader(lift) {
    if (!lift) {
      headerEl.innerHTML = '<div class="text-slate-500">Данные лифта не найдены.</div>';
      return;
    }
    headerEl.innerHTML = `
      <div class="text-slate-700 font-semibold text-base">${lift.lift_label || "Лифт без метки"}</div>
      <div class="text-slate-500">Серийный номер: <span class="text-slate-700">${lift.serial_no || "—"}</span></div>
      <div class="text-slate-500">Адрес: <span class="text-slate-700">${lift.address || "—"}</span></div>
      <div class="text-slate-500">Подъезд: <span class="text-slate-700">${lift.entrance || "—"}</span></div>
      <div class="text-slate-500">Статус: <span class="text-slate-700">${lift.status || "—"}</span></div>
    `;
  }

  function renderItems(items) {
    if (!items.length) {
      listEl.innerHTML = '<div class="text-sm text-slate-500">События за выбранный период не найдены.</div>';
      return;
    }
    listEl.innerHTML = items
      .map((item) => {
        const actor = item.actor ? `${item.actor.username} (${item.actor.role})` : "—";
        const ticketLink = `/admin?ui=admin&ticket_id=${item.ticket.id}`;
        return `
          <div class="relative pl-6 timeline-dot">
            <div class="flex flex-col gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="text-xs uppercase tracking-wide text-slate-500">${kindLabel(item.kind)}</div>
                <div class="text-xs text-slate-500">${formatDateTime(item.ts)}</div>
              </div>
              <div class="text-sm text-slate-700">${item.text || "—"}</div>
              <div class="text-xs text-slate-500">Исполнитель: <span class="text-slate-700">${actor}</span></div>
              <div class="text-xs text-slate-500">
                Заявка:
                <a href="${ticketLink}" class="text-slate-900 underline">
                  #${item.ticket.id} · ${item.ticket.title || "—"} (${item.ticket.status || "—"})
                </a>
              </div>
            </div>
          </div>
        `;
      })
      .join("");
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
      const res = await fetch(`/api/lifts/${assetId}/history${window.location.search}`, { cache: "no-store" });
      if (!res.ok) {
        stateEl.textContent = "Не удалось загрузить историю.";
        listEl.innerHTML = "";
        return;
      }
      const data = await res.json();
      setHeader(data.lift);
      renderItems(Array.isArray(data.items) ? data.items : []);
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

const listEl = document.getElementById("history-items");
const stateEl = document.getElementById("history-state");
const formEl = document.getElementById("history-filters");
const inputFrom = document.getElementById("history-from");
const inputTo = document.getElementById("history-to");
const resetBtn = document.getElementById("history-reset");
const statusFilterEl = document.getElementById("history-status-filter");

const STATUS_LABELS =
  typeof STATUS_RU !== "undefined"
    ? STATUS_RU
    : {
        COMPLETED: "Завершена",
        CANCELLED: "Отменена",
      };

const CLOSE_REASON_LABELS = {
  EQUIPMENT_FAILURE: "Неисправность оборудования",
  PASSENGER_TRAPPED: "Застрявший пассажир",
  FALSE_CALL: "Ложный вызов",
  POWER_ISSUE: "Проблема с питанием",
  EXTERNAL_REASON: "Внешняя причина",
  DUPLICATE: "Дубликат",
  NO_ACCESS: "Нет доступа",
  CUSTOMER_CANCELLED: "Отмена клиентом",
  OTHER: "Другое",
  UNSPECIFIED: "Не указана",
};

function formatStatus(status) {
  return STATUS_LABELS[status] || status || "—";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatCloseReason(reason) {
  return CLOSE_REASON_LABELS[reason] || reason || "—";
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", { hour12: false });
}

function getStatusParam(params) {
  return params.get("statuses") || params.get("status") || "COMPLETED,CANCELLED";
}

function renderStatusFilter(statuses) {
  const parts = statuses
    .split(",")
    .map((status) => status.trim())
    .filter(Boolean)
    .map((status) => formatStatus(status));
  if (!statusFilterEl) return;
  statusFilterEl.textContent = parts.length ? `Статусы: ${parts.join(", ")}` : "";
}

function updateUrlParams(dateFrom, dateTo) {
  const params = new URLSearchParams(window.location.search);
  if (dateFrom) {
    params.set("date_from", dateFrom);
  } else {
    params.delete("date_from");
  }
  if (dateTo) {
    params.set("date_to", dateTo);
  } else {
    params.delete("date_to");
  }
  history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

async function loadHistory() {
  if (!listEl || !stateEl) return;
  stateEl.textContent = "Загрузка...";
  listEl.innerHTML = "";

  const params = new URLSearchParams(window.location.search);
  const dateFrom = params.get("date_from") || "";
  const dateTo = params.get("date_to") || "";
  if (inputFrom) inputFrom.value = dateFrom;
  if (inputTo) inputTo.value = dateTo;

  const statuses = getStatusParam(params);
  renderStatusFilter(statuses);

  const apiParams = new URLSearchParams();
  apiParams.set("statuses", statuses);
  if (dateFrom) apiParams.set("date_from", dateFrom);
  if (dateTo) apiParams.set("date_to", dateTo);

  try {
    const res = await fetch(`/api/tickets/history?${apiParams.toString()}`, { cache: "no-store" });
    if (!res.ok) {
      stateEl.textContent = "Не удалось загрузить историю.";
      return;
    }
    const data = await res.json();
    const items = data.items || [];
    stateEl.textContent = items.length
      ? `Показано: ${items.length} из ${data.total ?? items.length}`
      : "Нет заявок по выбранному диапазону.";
    listEl.innerHTML = items
      .map((item) => {
        const reason = item.close_reason ? escapeHtml(formatCloseReason(item.close_reason)) : "—";
        const comment = item.close_comment
          ? `<div class="text-xs text-slate-500 mt-1">Комментарий: ${escapeHtml(item.close_comment)}</div>`
          : "";
        return `
          <div class="bg-white rounded-2xl shadow p-4">
            <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div class="text-sm font-semibold">#${item.id} — ${escapeHtml(item.object_name || "—")}</div>
                <div class="text-xs text-slate-500 mt-1">${escapeHtml(item.address || "—")}</div>
              </div>
              <div class="text-xs text-slate-500 text-right">
                <div>${formatStatus(item.status)}</div>
                <div>${formatDateTime(item.closed_at)}</div>
              </div>
            </div>
            <div class="mt-2 text-xs text-slate-600">
              <div>Мастер: ${escapeHtml(item.assigned_master_name || "—")}</div>
              <div>Причина: ${reason}</div>
              ${comment}
            </div>
          </div>
        `;
      })
      .join("");
  } catch (err) {
    stateEl.textContent = "Ошибка загрузки истории.";
  }
}

if (formEl) {
  formEl.addEventListener("submit", (event) => {
    event.preventDefault();
    const dateFrom = inputFrom ? inputFrom.value : "";
    const dateTo = inputTo ? inputTo.value : "";
    updateUrlParams(dateFrom, dateTo);
    loadHistory();
  });
}

if (resetBtn) {
  resetBtn.addEventListener("click", () => {
    if (inputFrom) inputFrom.value = "";
    if (inputTo) inputTo.value = "";
    updateUrlParams("", "");
    loadHistory();
  });
}

loadHistory();

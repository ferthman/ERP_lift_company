from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_admin_ticket_and_asset_renderers_escape_user_fields():
    source = read_repo_file("templates/index.html")

    assert "function escapeHtml(value)" in source
    assert "${escapeHtml(ticket.description ?? '—')}" in source
    assert "${escapeHtml(t.description ?? '')}" in source
    assert "${escapeHtml(t.object_name ?? '')}" in source
    assert "${escapeHtml(t.address ?? '')}" in source
    assert "${escapeHtml(renderAssetSummary(t) || '—')}" in source
    assert "${escapeHtml(asset.address || '—')}" in source
    assert "const customerLine = obj.customer_name ? `<div>Клиент: ${escapeHtml(obj.customer_name)}</div>` : '';" in source
    assert "const contractLine = obj.contract_title ? `<div>Договор: ${escapeHtml(obj.contract_title)}</div>` : '';" in source
    assert "circle.bindPopup(`<b>${escapeHtml(liftLabel)}</b><br>${escapeHtml(obj.address ?? '')}${entranceLine}${customerLine}${contractLine}`)" in source


def test_mobile_ticket_and_history_renderers_escape_user_fields():
    source = read_repo_file("static/mobile.js")

    assert "function escapeHtml(value)" in source
    assert '${escapeHtml(ticket.object_name || "Заявка")}' in source
    assert '${escapeHtml(ticket.address || "Адрес не указан")}' in source
    assert '${escapeHtml(ticket.description || "—")}' in source
    assert "${escapeHtml(c.body)}" in source
    assert '${escapeHtml(event.body || "—")}' in source


def test_history_pages_escape_comments_addresses_and_event_text():
    history = read_repo_file("static/history.js")
    lift_history = read_repo_file("static/lift_history.js")
    lift_detail = read_repo_file("static/lift_detail.js")

    assert "Комментарий: ${escapeHtml(item.close_comment)}" in history
    assert '${escapeHtml(item.object_name || "—")}' in history
    assert '${escapeHtml(item.address || "—")}' in history
    assert '${escapeHtml(lift.address || "—")}' in lift_history
    assert '${escapeHtml(item.text || "—")}' in lift_history
    assert '${escapeHtml(item.ticket.title || "—")}' in lift_history
    assert '${escapeHtml(lift.address || "—")}' in lift_detail
    assert '${escapeHtml(event.text || "—")}' in lift_detail
    assert "${escapeHtml(ticketTitle(ticket))}" in lift_detail

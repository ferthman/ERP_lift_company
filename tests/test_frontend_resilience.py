from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_admin_header_is_responsive_on_narrow_viewports():
    source = read_repo_file("templates/index.html")

    assert "data-app-nav" in source
    assert "overflow-x-auto" in source
    assert 'id="menu-toggle"' in source
    assert "@media(max-width:800px)" in read_repo_file("static/crm.css")
    assert "[data-app-nav] > button{flex:0 0 auto;white-space:nowrap}" in source


def test_admin_modals_can_scroll_on_mobile_viewports():
    source = read_repo_file("templates/index.html")

    assert source.count("max-h-[92vh] overflow-y-auto") >= 7


def test_admin_map_handles_missing_leaflet_and_failed_assets_fetch():
    source = read_repo_file("templates/index.html")

    assert "function isLeafletAvailable()" in source
    assert "renderMapUnavailable(document.getElementById('map-create')" in source
    assert "renderMapUnavailable(document.getElementById('objects-map')" in source
    assert "Карта временно недоступна" in source
    assert "Не удалось загрузить объекты карты" in source
    assert "В реестре нет лифтов с координатами" in source
    assert "if(!objectsMap || !isLeafletAvailable()) return;" in source


def test_closed_tickets_do_not_show_remaining_sla_minutes():
    source = read_repo_file("templates/index.html")

    assert "const isClosed = ['COMPLETED','CANCELLED'].includes(t.status);" in source
    assert "SLA был просрочен" in source
    assert "return showPlaceholder ? '—' : '';" in source

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_service_worker_does_not_cache_api_or_authenticated_responses():
    source = read_repo_file("static/sw.js")

    assert "caches.match(e.request)" not in source
    assert "pathname.startsWith(\"/api/\")" in source
    assert "pathname.startsWith(\"/uploads/\")" in source
    assert "[\"/\", \"/admin\", \"/login\", \"/logout\", \"/mobile\"].includes(url.pathname)" in source
    assert "event.respondWith(fetch(request));" in source
    assert "STATIC_SHELL_URLS.includes(url.pathname)" in source


def test_service_worker_makes_deploy_updates_predictable():
    source = read_repo_file("static/sw.js")

    assert "const CACHE_NAME = \"liftcrm-shell-v8\"" in source
    assert "self.skipWaiting()" in source
    assert "self.clients.claim()" in source
    assert "caches.delete(name)" in source


def test_mobile_failed_outbox_is_visible_retryable_and_discardable():
    template = read_repo_file("templates/mobile.html")
    source = read_repo_file("static/mobile.js")

    assert ".mobile-action-grid button:disabled" in template
    assert "id=\"outbox-panel\"" in template
    assert "id=\"outbox-failed-list\"" in template
    assert "id=\"outbox-retry-all\"" in template
    assert "mobile-action-grid grid grid-cols-2 gap-2" in source
    assert "async function retryOutboxEvent" in source
    assert "async function discardOutboxEvent" in source
    assert "async function retryAllFailedOutbox" in source
    assert "renderFailedOutbox(events, photos)" in source
    assert "event.status = \"pending\"" in source
    assert "await deleteOutboxEvent(item.id)" in source
    assert "CONFLICT: \"Заявка изменилась на сервере\"" in source
    assert "OUT_OF_RANGE: \"Вы вне геозоны объекта\"" in source


def test_mobile_transient_failures_stay_pending_and_photo_queue_is_bounded():
    source = read_repo_file("static/mobile.js")

    assert "globalThis.crypto?.randomUUID" in source
    assert "const MAX_PHOTO_SIZE_BYTES = 8 * 1024 * 1024" in source
    assert "const MAX_QUEUED_PHOTOS = 20" in source
    assert "file.size > MAX_PHOTO_SIZE_BYTES" in source
    assert "queuedPhotos.length >= MAX_QUEUED_PHOTOS" in source
    assert "photo.status = \"error\"" in source
    assert "Transient network failures stay pending" in source
    assert "retryOutboxPhoto" in source
    assert "discardOutboxPhoto" in source


def test_mobile_reset_requires_confirmation_before_clearing_outbox():
    source = read_repo_file("static/mobile.js")

    assert "const queuedCount = events.length + photos.length" in source
    assert "window.confirm(message)" in source
    assert "if (!window.confirm(message)) return;" in source
    assert "несинхронизированных действий/фото" in source


def test_mobile_shell_has_root_scope_and_separate_identity():
    source=read_repo_file("static/mobile.js")
    worker=read_repo_file("static/sw.js")
    assert "register(\"/sw.js\",{scope:'/'})" in source
    assert 'liftcrm-mobile-${mobileIdentity?.id' in source
    assert "headers.set('X-Mobile-User'" in source
    assert 'verifyIdentity()' in source
    assert "cache.match('/mobile-shell')" in worker
    assert "cache.put(request" not in worker

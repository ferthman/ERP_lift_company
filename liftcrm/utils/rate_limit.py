import threading
import time
from collections import deque


_RATE_LIMITS: dict[str, deque[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()


def check_rate_limit(key: str, limit: int, window_seconds: int) -> tuple[bool, dict]:
    now = time.time()
    with _RATE_LIMIT_LOCK:
        timestamps = _RATE_LIMITS.get(key)
        if timestamps is None:
            timestamps = deque()
            _RATE_LIMITS[key] = timestamps
        while timestamps and (now - timestamps[0]) >= window_seconds:
            timestamps.popleft()
        count = len(timestamps)
        if count >= limit:
            reset_in_seconds = max(0, int(window_seconds - (now - timestamps[0]))) if timestamps else window_seconds
            return False, {"remaining": 0, "reset_in_seconds": reset_in_seconds, "count": count}
        timestamps.append(now)
        count = len(timestamps)
        reset_in_seconds = max(0, int(window_seconds - (now - timestamps[0]))) if timestamps else window_seconds
        return True, {"remaining": max(0, limit - count), "reset_in_seconds": reset_in_seconds, "count": count}


def clear_rate_limits() -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMITS.clear()


def get_client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""

import logging
import os


def setup_logging():
    """
    Initialize a simple console logger for the app. Idempotent.
    Level can be overridden via LOG_LEVEL env var (default INFO).
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return logging.getLogger("liftcrm")

import atexit
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from liftcrm import config

TEST_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="erp-lift-tests-"))

config.DB_PATH = str(TEST_ROOT / "lift_crm_test.db")
config.ARCHIVE_PATH = str(TEST_ROOT / "archive.xlsx")
config.UPLOAD_FOLDER = str(TEST_ROOT / "uploads")
pathlib.Path(config.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

atexit.register(shutil.rmtree, TEST_ROOT, ignore_errors=True)

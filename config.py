"""Settings, read from environment variables (or a local .env file)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEBUG_DIR = BASE_DIR / "debug"


def _load_dotenv() -> None:
    """Tiny .env reader so no extra package is needed."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
# Optional: if empty, the bot remembers the channel automatically when you make it a channel admin.
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()}
# Optional: when set, data is saved encrypted (needed when the code lives in a public GitHub repo).
STATE_KEY = os.environ.get("STATE_KEY", "").strip()

# Checking behaviour
DEFAULT_USER_LINK_LIMIT = int(os.environ.get("USER_LINK_LIMIT", "5"))
LOCAL_LOOP_MINUTES = int(os.environ.get("CHECK_EVERY_MINUTES", "20"))
PAUSE_BETWEEN_PAGES = (2.0, 4.0)  # seconds, random wait between page loads (be gentle with Zepto)
MAX_RUN_SECONDS = int(os.environ.get("MAX_RUN_SECONDS", str(16 * 60)))
# Zepto shows a blank page to headless browsers, so a normal (visible) browser is the default.
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
# Open the visible browser window outside the screen so it does not disturb you (set 0 to watch it).
HIDE_WINDOW = os.environ.get("HIDE_WINDOW", "1") != "0"

"""Load/save all bot data in one JSON file (optionally encrypted with STATE_KEY)."""
import json
import time

import config

PLAIN_FILE = config.DATA_DIR / "state.json"
ENC_FILE = config.DATA_DIR / "state.enc"
LOCATIONS_FILE = config.DATA_DIR / "locations.json"
PRODUCTS_FILE = config.DATA_DIR / "products.json"  # starting product list (only used on the very first run)


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(config.STATE_KEY.encode())


def _default_state() -> dict:
    locations = []
    if LOCATIONS_FILE.exists():
        locations = json.loads(LOCATIONS_FILE.read_text(encoding="utf-8"))
    products = []
    if PRODUCTS_FILE.exists():
        from zepto import clean_url, extract_pvid
        for p in json.loads(PRODUCTS_FILE.read_text(encoding="utf-8")):
            pvid = extract_pvid(p["url"])
            if pvid:
                products.append({"pvid": pvid, "url": clean_url(p["url"]), "name": p.get("name"),
                                 "custom_name": bool(p.get("name"))})
    return {
        "update_offset": 0,
        "channel_id": "",
        "settings": {"user_link_limit": config.DEFAULT_USER_LINK_LIMIT},
        "locations": locations,      # admin locations, alerts go to the channel
        "channel_products": products,  # [{pvid, url, name}]
        "users": {},                 # chat_id -> {name, pincode, products:[...], blocked}
        "status": {},                # "pvid|loc_key" -> {in_stock, qty, store, ts}
        "pin_status": {},
        "loc_place": {},             # loc_key -> exact address Zepto picked            # "pin:110001" -> {serviceable, store, ts}
    }


def load() -> dict:
    state = None
    if config.STATE_KEY and ENC_FILE.exists():
        state = json.loads(_fernet().decrypt(ENC_FILE.read_bytes()).decode("utf-8"))
    elif not config.STATE_KEY and PLAIN_FILE.exists():
        state = json.loads(PLAIN_FILE.read_text(encoding="utf-8"))
    base = _default_state()
    if state is None:
        return base
    for key, value in base.items():
        state.setdefault(key, value)
    return state


def save(state: dict) -> bool:
    """Write the state. Returns True if the file actually changed."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True)
    if config.STATE_KEY:
        if ENC_FILE.exists():
            try:
                if _fernet().decrypt(ENC_FILE.read_bytes()).decode("utf-8") == text:
                    return False
            except Exception:
                pass
        ENC_FILE.write_bytes(_fernet().encrypt(text.encode("utf-8")))
        return True
    if PLAIN_FILE.exists() and PLAIN_FILE.read_text(encoding="utf-8") == text:
        return False
    PLAIN_FILE.write_text(text, encoding="utf-8")
    return True


def now() -> int:
    return int(time.time())

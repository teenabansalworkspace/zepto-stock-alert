import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["ADMIN_IDS"] = "999"

import config  # noqa: E402
config.ADMIN_IDS = {999}
config.CHANNEL_ID = ""
config.PAUSE_BETWEEN_PAGES = (0, 0)

import bot_commands  # noqa: E402
import runner  # noqa: E402
import storage  # noqa: E402
import zepto  # noqa: E402

PVID = "eb012377-49a9-4980-9af5-f66648195768"
OTHER = "11111111-2222-3333-4444-555555555555"
URL = f"https://www.zepto.com/pn/oppo-k14x/pvid/{PVID}?marketplaceType=SUPER_SAVER&utm=x"


def page_html(main_qty, rec_qty=7):
    """Mimics the real page: data inside escaped JS strings, main product then a recommendation."""
    main_sp = f'\\"availableQuantity\\":{main_qty},\\"discountApplicable\\":true' if main_qty else '\\"discountApplicable\\":true'
    payload = (f'{{\\"productVariant\\":{{\\"id\\":\\"{PVID}\\",\\"name\\":\\"Oppo\\",\\"weightInGms\\":212}},'
               f'\\"storeProduct\\":{{{main_sp}}},\\"isOutOfStock\\":{"false" if main_qty else "true"},'
               f'\\"rec\\":{{\\"productVariant\\":{{\\"id\\":\\"{OTHER}\\"}},\\"storeProduct\\":{{\\"availableQuantity\\":{rec_qty}}}}}}}')
    ld = json.dumps({"@context": "https://schema.org", "@type": "Product", "name": "Oppo K14x 5G | Prism Violet"})
    return (f'<html><head><title>Oppo K14x 5G Smartphone - Buy at ₹17999 Online</title>'
            f'<script type="application/ld+json">{ld}</script></head><body>'
            f'<script>self.__next_f.push([1,"{payload}"])</script></body></html>')


# ------------------------------------------------------------- parsing
def test_extract_pvid_and_clean_url():
    assert zepto.extract_pvid(URL) == PVID
    assert zepto.extract_pvid("https://amazon.in/x") is None
    assert zepto.clean_url(URL) == f"https://www.zepto.com/pn/oppo-k14x/pvid/{PVID}?marketplaceType=SUPER_SAVER"


def test_parse_in_stock_uses_main_product_not_recommendation():
    p = zepto.parse_product_page(page_html(3), PVID)
    assert p["qty"] == 3 and p["oos_flag"] is False
    assert p["name"] == "Oppo K14x 5G | Prism Violet"


def test_parse_out_of_stock_ignores_recommendation_qty():
    p = zepto.parse_product_page(page_html(0, rec_qty=9), PVID)
    assert p["qty"] == 0 and p["oos_flag"] is True


def test_decide_stock():
    assert zepto.decide_stock("add", {"qty": 4}) == (True, 4)
    assert zepto.decide_stock("add", {"qty": None}) == (True, None)
    assert zepto.decide_stock("notify", {"qty": 4}) == (False, 0)
    assert zepto.decide_stock("none", {"qty": 2}) == (True, 2)
    assert zepto.decide_stock("none", {"qty": None, "oos_flag": True}) == (False, None)
    assert zepto.decide_stock("none", {"qty": None, "oos_flag": None}) == (None, None)


def test_parse_serviceability_cookie():
    raw = "%7B%22primaryStore%22%3A%7B%22isDeliverable%22%3Atrue%2C%22serviceable%22%3Atrue%2C%22storeId%22%3A%22abc%22%7D%7D"
    assert zepto.parse_serviceability(raw) == {"serviceable": True, "deliverable": True, "store": "abc"}
    assert zepto.parse_serviceability("garbage")["serviceable"] is False


# ------------------------------------------------------------- bot commands
def fresh_state():
    s = storage._default_state()
    s["locations"] = [{"id": "dl-cp", "label": "Delhi CP", "query": "110001"},
                      {"id": "up-noida", "label": "Noida", "query": "201301"}]
    return s


def msg(chat_id, text):
    return {"message": {"chat": {"id": chat_id, "type": "private"}, "from": {"id": chat_id, "first_name": "Riya"},
                        "text": text}}


class Outbox(list):
    def __call__(self, chat, text):
        self.append((chat, text))
        return True


def test_user_flow_and_limits():
    s, out = fresh_state(), Outbox()
    bot_commands.handle_update(s, msg(5, f"/add {URL}"), out)
    assert "pincode" in out[-1][1].lower()
    bot_commands.handle_update(s, msg(5, "/pincode 12345"), out)
    assert s["users"]["5"]["pincode"] is None
    bot_commands.handle_update(s, msg(5, "/pincode 201301"), out)
    bot_commands.handle_update(s, msg(5, f"/add {URL} Mera Oppo"), out)
    u = s["users"]["5"]
    assert u["products"][0]["name"] == "Mera Oppo" and u["products"][0]["custom_name"]
    bot_commands.handle_update(s, msg(5, f"/add {URL}"), out)
    assert "pehle se" in out[-1][1]
    s["settings"]["user_link_limit"] = 1
    bot_commands.handle_update(s, msg(5, f"/add https://www.zepto.com/pn/x/pvid/{OTHER}"), out)
    assert "max 1" in out[-1][1]
    before = list(s["channel_products"])
    bot_commands.handle_update(s, msg(5, f"/addproduct https://www.zepto.com/pn/x/pvid/{OTHER}"), out)  # not admin
    assert s["channel_products"] == before
    bot_commands.handle_update(s, msg(5, "/remove 1"), out)
    assert u["products"] == []


def test_admin_commands_and_channel_autodetect():
    s, out = fresh_state(), Outbox()
    bot_commands.handle_update(s, msg(999, f"/addproduct {URL}"), out)
    assert s["channel_products"][0]["pvid"] == PVID
    bot_commands.handle_update(s, msg(999, "/addloc 302017 Jaipur Malviya Nagar"), out)
    assert s["locations"][-1]["label"] == "Jaipur Malviya Nagar"
    bot_commands.handle_update(s, msg(999, "/removeloc 3"), out)
    assert len(s["locations"]) == 2
    bot_commands.handle_update(s, msg(5, "/start"), out)
    bot_commands.handle_update(s, msg(999, "/block 5"), out)
    assert s["users"]["5"]["blocked"]
    n = len(out)
    bot_commands.handle_update(s, msg(5, "/mylist"), out)
    assert len(out) == n  # blocked users get no reply
    bot_commands.handle_update(s, {"my_chat_member": {"chat": {"id": -100123, "type": "channel", "title": "Alerts"},
                                                       "from": {"id": 999},
                                                       "new_chat_member": {"status": "administrator"}}}, out)
    assert s["channel_id"] == -100123


# ------------------------------------------------------------- check round with a fake Zepto
class FakeChecker:
    def __init__(self, stock):  # stock: {(query, pvid): (in_stock, qty)}
        self.stock, self.loads = stock, []

    def open_location(self, query):
        store = {"110001": "S1", "201301": "S2", "201310": "S2", "999999": None}[query]
        page = {"query": query}
        return None, page, {"serviceable": store is not None, "store": store, "deliverable": True}

    def check_product(self, page, url, pvid):
        self.loads.append((page["query"], pvid))
        in_stock, qty = self.stock.get((page["query"], pvid), (False, 0))
        return {"in_stock": in_stock, "qty": qty, "name": "Oppo K14x 5G"}


def test_round_alerts_only_on_restock_and_dedupes_store():
    s, out = fresh_state(), Outbox()
    s["channel_id"] = -100123
    s["channel_products"] = [{"pvid": PVID, "url": URL, "name": None, "custom_name": False}]
    s["users"]["5"] = {"name": "Riya", "pincode": "201310", "blocked": False,
                       "products": [{"pvid": PVID, "url": URL, "name": "Mera", "custom_name": True}]}
    s["users"]["6"] = {"name": "X", "pincode": "999999", "blocked": False,
                       "products": [{"pvid": PVID, "url": URL, "name": None, "custom_name": False}]}

    fake = FakeChecker({})
    runner.run_checks(s, fake, send=out)
    assert not [m for m in out if "stock aaya" in m[1] or "stock mein aa gaya" in m[1]]
    assert any("service nahi" in m[1] and m[0] == "6" for m in out)
    # 201301 and 201310 share store S2 -> product page loaded only once for S2
    assert fake.loads.count(("201301", PVID)) + fake.loads.count(("201310", PVID)) == 1
    assert s["channel_products"][0]["name"] == "Oppo K14x 5G"       # name learnt from page
    assert s["users"]["5"]["products"][0]["name"] == "Mera"          # custom name kept

    out.clear()
    fake = FakeChecker({("201301", PVID): (True, 3), ("201310", PVID): (True, 3)})
    runner.run_checks(s, fake, send=out)
    ch = [m for m in out if m[0] == -100123]
    assert len(ch) == 1 and "Noida (201301) – 3 pcs 🆕" in ch[0][1] and "Delhi CP" not in ch[0][1]
    dm = [m for m in out if m[0] == "5"]
    assert len(dm) == 1 and "201310" in dm[0][1]
    assert not any("service nahi" in m[1] for m in out)  # warned only once

    out.clear()
    runner.run_checks(s, fake, send=out)  # still in stock -> no repeat alert
    assert not [m for m in out if m[0] in (-100123, "5")]


def test_storage_encrypted_roundtrip(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "ENC_FILE", tmp_path / "state.enc")
    monkeypatch.setattr(config, "STATE_KEY", Fernet.generate_key().decode())
    s = fresh_state()
    s["users"]["5"] = {"name": "Riya"}
    assert storage.save(s) is True
    assert b"Riya" not in (tmp_path / "state.enc").read_bytes()
    assert storage.save(s) is False  # unchanged -> no rewrite (no useless commit)
    assert storage.load()["users"]["5"]["name"] == "Riya"

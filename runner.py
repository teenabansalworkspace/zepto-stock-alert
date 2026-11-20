"""One check round: decide what to check, check it on Zepto, and send alerts."""
import time
from datetime import datetime, timedelta, timezone

import config
import storage
import telegram_api as tg
from telegram_api import esc

IST = timezone(timedelta(hours=5, minutes=30))


def build_plan(state: dict) -> list:
    """List of locations to visit, each with the products to check there."""
    plan = {}
    for loc in state["locations"]:
        if state["channel_products"]:
            entry = plan.setdefault(loc["id"], {"key": loc["id"], "query": loc["query"], "label": loc["label"],
                                                "kind": "channel", "products": {}})
            for p in state["channel_products"]:
                entry["products"][p["pvid"]] = p["url"]
    for u in state["users"].values():
        pin = u.get("pincode")
        if u.get("blocked") or not pin or not u.get("products"):
            continue
        entry = plan.setdefault(f"pin:{pin}", {"key": f"pin:{pin}", "query": pin, "label": pin,
                                               "kind": "user", "products": {}})
        for p in u["products"]:
            entry["products"][p["pvid"]] = p["url"]
    return list(plan.values())


def apply_result(state: dict, loc_key: str, pvid: str, result: dict, store) -> bool:
    """Save a check result. Returns True if the product has just come (back) in stock."""
    if result.get("in_stock") is None:
        return False  # could not read the page; keep the old status
    skey = f"{pvid}|{loc_key}"
    before = state["status"].get(skey)
    state["status"][skey] = {"in_stock": result["in_stock"], "qty": result.get("qty"),
                             "store": store, "ts": storage.now()}
    return bool(result["in_stock"]) and not (before and before.get("in_stock"))


def update_names(state: dict, pvid: str, name: str) -> None:
    if not name:
        return
    lists = [state["channel_products"]] + [u["products"] for u in state["users"].values()]
    for products in lists:
        for p in products:
            if p["pvid"] == pvid and not p.get("custom_name"):
                p["name"] = name


def _qty_text(qty) -> str:
    return f"{qty} pcs" if qty else "qty nahi dikhayi"


def channel_message(state: dict, product: dict, new_locs: set) -> str:
    lines = ["🟢 <b>Zepto pe stock aaya!</b>",f"<b>{esc(product.get('name') or 'Zepto product')}</b>", "", "📍 Kahan available hai:"]
    for loc in state["locations"]:
        st = state["status"].get(f"{product['pvid']}|{loc['id']}")
        if st and st.get("in_stock"):
            tag = " 🆕" if loc["id"] in new_locs else ""
            lines.append(f"• {esc(loc['label'])} – {_qty_text(st.get('qty'))}{tag}")
            place = state.get("loc_place", {}).get(loc["id"])
            if place:
                lines.append(f"   📌 Zepto address: {esc(place)}")
    lines += ["", f"🔗 {esc(product['url'])}", f"🕒 {datetime.now(IST):%d %b %Y, %I:%M %p} IST"]
    return "\n".join(lines)


def user_message(product: dict, pin: str, st: dict, place=None) -> str:
    return "\n".join([
        "🟢 <b>Aapka product Zepto pe stock mein aa gaya!</b>",
        f"<b>{esc(product.get('name') or 'Zepto product')}</b>",
        f"📍 Pincode {pin} – {_qty_text(st.get('qty'))}",
    ] + ([f"📌 Zepto address: {esc(place)}"] if place else []) + [
        f"🔗 {esc(product['url'])}",
        f"🕒 {datetime.now(IST):%d %b %Y, %I:%M %p} IST",
    ])


def run_checks(state: dict, checker, send=tg.send) -> dict:
    """Visit every location in the plan. `checker` is a ZeptoChecker (or a fake in tests)."""
    started = time.time()
    plan = build_plan(state)
    if not plan:
        print("[run] kuch check karne ko nahi hai (koi product/location nahi)")
        return {"checked": 0}

    # Rotate the starting point so that, if time runs out, the next round starts with the skipped ones.
    start = state.get("rotation", 0) % len(plan)
    plan = plan[start:] + plan[:start]

    cache = {}  # (store, pvid) -> result, so one dark store is checked once per round
    new_channel = {}  # pvid -> set(loc_id)
    new_user = []     # (loc_key, pvid)
    checked = visited = fails = 0

    for entry in plan:
        if time.time() - started > config.MAX_RUN_SECONDS:
            print("[run] time limit, baaki agle round mein")
            break
        visited += 1
        ctx = None
        try:
            ctx, page, info = checker.open_location(entry["query"])
            if info.get("place"):
                state.setdefault("loc_place", {})[entry["key"]] = info["place"]
                print(f"[run] {entry['label']}: Zepto address = {info['place']}")
            if entry["kind"] == "user":
                prev = state["pin_status"].get(entry["key"], {})
                state["pin_status"][entry["key"]] = {"serviceable": info["serviceable"], "store": info["store"],
                                                     "ts": storage.now(), "warned": prev.get("warned", False)}
            if not info["serviceable"] or not info["store"]:
                print(f"[run] {entry['label']}: Zepto yahan serviceable nahi")
                if entry["kind"] == "user" and not state["pin_status"][entry["key"]]["warned"]:
                    for uid, u in state["users"].items():
                        if u.get("pincode") == entry["query"] and not u.get("blocked"):
                            send(uid, f"⚠️ Zepto pincode {entry['query']} pe service nahi deta lag raha. "
                                      f"Koi nazdeeki pincode try karein: <code>/pincode XXXXXX</code>")
                    state["pin_status"][entry["key"]]["warned"] = True
                continue
            for pvid, url in entry["products"].items():
                ck = (info["store"], pvid)
                if ck in cache:
                    result = cache[ck]
                else:
                    try:
                        result = checker.check_product(page, url, pvid)
                    except Exception as exc:
                        print(f"[run] {entry['label']} {pvid}: page error {exc}")
                        continue
                    cache[ck] = result
                    checked += 1
                update_names(state, pvid, result.get("name"))
                if apply_result(state, entry["key"], pvid, result, info["store"]):
                    if entry["kind"] == "channel":
                        new_channel.setdefault(pvid, set()).add(entry["key"])
                    else:
                        new_user.append((entry["key"], pvid))
                print(f"[run] {entry['label']:<28} {pvid[:8]} -> "
                      f"{'IN' if result.get('in_stock') else 'out' if result.get('in_stock') is False else '??'} "
                      f"qty={result.get('qty')}")
            fails = 0
        except Exception as exc:
            print(f"[run] {entry['label']}: location error {str(exc).splitlines()[0]}")
            fails += 1
            if fails >= 3:
                print("[run] 3 locations lagatar fail – Zepto page nahi khul raha, ye round rok rahe hain. "
                      "'python main.py debug' chala kar dekhein.")
                break
        finally:
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:
                    pass

    state["rotation"] = (start + visited) % max(len(plan), 1) if visited < len(plan) else 0

    # ---- alerts
    channel = config.CHANNEL_ID or state.get("channel_id")
    for pvid, locs in new_channel.items():
        product = next((p for p in state["channel_products"] if p["pvid"] == pvid), None)
        if product and channel:
            send(channel, channel_message(state, product, locs))
        elif product:
            print("[run] channel set nahi hai, alert nahi bheja")
    for loc_key, pvid in new_user:
        pin = loc_key.split(":", 1)[1]
        st = state["status"][f"{pvid}|{loc_key}"]
        for uid, u in state["users"].items():
            if u.get("blocked") or u.get("pincode") != pin:
                continue
            product = next((p for p in u["products"] if p["pvid"] == pvid), None)
            if product:
                send(uid, user_message(product, pin, st, state.get("loc_place", {}).get(loc_key)))

    state["last_run"] = storage.now()
    return {"checked": checked, "locations": visited, "channel_alerts": len(new_channel), "user_alerts": len(new_user)}

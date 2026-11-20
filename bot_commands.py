"""Handles the Telegram commands that users and admins send to the bot."""
import re

import config
import storage
import telegram_api as tg
from telegram_api import esc
from zepto import clean_url, extract_pvid

USER_HELP = (
    "👋 <b>Zepto Stock Alert Bot</b>\n\n"
    "Jab aapka product Zepto pe stock mein aayega, main aapko yahin message karunga.\n\n"
    "1️⃣ Pehle apna pincode set karein:\n<code>/pincode 110001</code>\n"
    "2️⃣ Phir product link bhejein (naam optional):\n<code>/add https://www.zepto.com/pn/.../pvid/... Mera phone</code>\n\n"
    "Other commands:\n"
    "/mylist – aapke products\n"
    "/remove 2 – list ka 2nd product hatayein\n"
    "/status – aapke products ka last status\n"
    "/myid – aapki Telegram ID\n\n"
    "ℹ️ Bot har ~20 minute mein check karta hai, isliye jawab aane mein thoda time lag sakta hai."
)

ADMIN_HELP = (
    "🛠 <b>Admin commands</b> (channel ke liye)\n"
    "/addproduct &lt;link&gt; [naam] – channel list mein product jodein\n"
    "/products – channel products\n"
    "/removeproduct 2 – channel product hatayein\n"
    "/locs – channel locations\n"
    "/addloc &lt;pincode&gt; [label] – location jodein\n"
    "/removeloc 3 – location hatayein\n"
    "/users – sab users\n"
    "/block &lt;id&gt; | /unblock &lt;id&gt;\n"
    "/setlimit 5 – har user kitne links add kar sake\n"
    "/overview – channel products abhi kahan stock mein hain"
)


def is_admin(user_id) -> bool:
    return int(user_id) in config.ADMIN_IDS


def _product_from_args(args: str):
    """'<link> optional name' -> dict or None"""
    m = re.search(r"https?://\S+", args or "")
    if not m:
        return None
    url = m.group(0)
    pvid = extract_pvid(url)
    if not pvid:
        return None
    name = (args[:m.start()] + args[m.end():]).strip() or None
    return {"pvid": pvid, "url": clean_url(url), "name": name, "custom_name": bool(name)}


def _fmt_list(products) -> str:
    if not products:
        return "(khaali)"
    return "\n".join(f"{i}. {esc(p.get('name') or 'Zepto product')}\n   {esc(p['url'])}"
                     for i, p in enumerate(products, 1))


def _pick_index(arg: str, items):
    if not arg.strip().isdigit():
        return None
    idx = int(arg.strip()) - 1
    return idx if 0 <= idx < len(items) else None


def handle_update(state: dict, update: dict, send=tg.send) -> None:
    # Bot was added to / removed from a channel
    member = update.get("my_chat_member")
    if member:
        chat = member.get("chat", {})
        status = member.get("new_chat_member", {}).get("status")
        by = member.get("from", {}).get("id")
        if chat.get("type") == "channel" and status == "administrator" and is_admin(by):
            state["channel_id"] = chat["id"]
            send(by, f"✅ Channel connect ho gaya: <b>{esc(chat.get('title', ''))}</b>\nAb alerts yahin jayenge.")
        return

    msg = update.get("message")
    if not msg or "text" not in msg:
        return
    chat_id = msg["chat"]["id"]
    if msg["chat"].get("type") != "private":
        return  # commands only in private chat with the bot
    user = msg.get("from", {})
    text = msg["text"].strip()
    cmd, _, args = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    key = str(chat_id)

    users = state["users"]
    u = users.get(key)
    if u is None:
        u = users[key] = {"name": (user.get("first_name") or "") + (" " + user["last_name"] if user.get("last_name") else ""),
                          "username": user.get("username"), "pincode": None, "products": [],
                          "blocked": False, "joined": storage.now()}
    if u.get("blocked") and not is_admin(chat_id):
        return

    admin = is_admin(chat_id)

    if cmd in ("/start", "/help"):
        send(chat_id, USER_HELP + ("\n\n" + ADMIN_HELP if admin else ""))

    elif cmd == "/myid":
        send(chat_id, f"Aapki Telegram ID: <code>{chat_id}</code>")

    elif cmd == "/pincode":
        pin = args.strip()
        if not re.fullmatch(r"[1-9]\d{5}", pin):
            send(chat_id, "Sahi 6-digit pincode bhejein, jaise: <code>/pincode 201301</code>")
            return
        u["pincode"] = pin
        send(chat_id, f"📍 Pincode set: <b>{pin}</b>\nAb <code>/add &lt;zepto link&gt;</code> se product jodein.")

    elif cmd == "/add":
        if not u.get("pincode"):
            send(chat_id, "Pehle pincode set karein: <code>/pincode 110001</code>")
            return
        product = _product_from_args(args)
        if not product:
            send(chat_id, "Ye Zepto product link nahi lag raha. Link mein <code>/pvid/</code> hona chahiye.")
            return
        if any(p["pvid"] == product["pvid"] for p in u["products"]):
            send(chat_id, "Ye product pehle se aapki list mein hai.")
            return
        limit = state["settings"].get("user_link_limit", config.DEFAULT_USER_LINK_LIMIT)
        if len(u["products"]) >= limit and not admin:
            send(chat_id, f"Aap max {limit} products rakh sakte hain. Pehle /remove se koi hatayein.")
            return
        u["products"].append(product)
        send(chat_id, f"✅ Jod diya. Pincode {u['pincode']} pe stock aate hi bataunga.\n"
                      f"(Pehla check agle round mein hoga.)")

    elif cmd == "/mylist":
        send(chat_id, f"📍 Pincode: {u.get('pincode') or 'set nahi'}\n\n" + _fmt_list(u["products"]))

    elif cmd == "/remove":
        idx = _pick_index(args, u["products"])
        if idx is None:
            send(chat_id, "Number bhejein, jaise <code>/remove 1</code> (/mylist dekhein)")
            return
        removed = u["products"].pop(idx)
        send(chat_id, f"🗑 Hata diya: {esc(removed.get('name') or removed['url'])}")

    elif cmd == "/status":
        pin = u.get("pincode")
        if not pin or not u["products"]:
            send(chat_id, "Aapki list khaali hai ya pincode set nahi hai.")
            return
        ps = state["pin_status"].get(f"pin:{pin}")
        lines = []
        if ps and ps.get("serviceable") is False:
            lines.append(f"⚠️ Zepto pincode {pin} pe service nahi deta lag raha.")
        for i, p in enumerate(u["products"], 1):
            st = state["status"].get(f"{p['pvid']}|pin:{pin}")
            if not st:
                s = "⏳ abhi check nahi hua"
            elif st.get("in_stock"):
                s = "🟢 In stock" + (f" ({st['qty']} pcs)" if st.get("qty") else "")
            else:
                s = "🔴 Out of stock"
            lines.append(f"{i}. {esc(p.get('name') or 'Zepto product')} – {s}")
        send(chat_id, "\n".join(lines))

    # ---------------- admin only
    elif not admin:
        send(chat_id, "Ye command samajh nahi aaya. /help dekhein.")

    elif cmd == "/addproduct":
        product = _product_from_args(args)
        if not product:
            send(chat_id, "Format: <code>/addproduct &lt;zepto link&gt; [naam]</code>")
            return
        if any(p["pvid"] == product["pvid"] for p in state["channel_products"]):
            send(chat_id, "Ye product pehle se channel list mein hai.")
            return
        state["channel_products"].append(product)
        send(chat_id, f"✅ Channel list mein joda ({len(state['channel_products'])} products).")

    elif cmd == "/products":
        send(chat_id, "📦 Channel products:\n" + _fmt_list(state["channel_products"]))

    elif cmd == "/removeproduct":
        idx = _pick_index(args, state["channel_products"])
        if idx is None:
            send(chat_id, "Number bhejein, jaise <code>/removeproduct 1</code>")
            return
        removed = state["channel_products"].pop(idx)
        send(chat_id, f"🗑 Hata diya: {esc(removed.get('name') or removed['url'])}")

    elif cmd == "/locs":
        lines = [f"{i}. {esc(l['label'])} ({l['query']})" for i, l in enumerate(state["locations"], 1)]
        send(chat_id, "📍 Channel locations:\n" + ("\n".join(lines) or "(khaali)"))

    elif cmd == "/addloc":
        # "/addloc 122001 Gurugram Sec 14"  -> search by pincode, custom label
        # "/addloc Sector 29 Gurugram"       -> search exactly this area name on Zepto
        args = args.strip()
        first, _, rest = args.partition(" ")
        if re.fullmatch(r"[1-9]\d{5}", first):
            query, label = first, (rest.strip() or first)
        else:
            query = label = args
        if len(query) < 3:
            send(chat_id, "Format: <code>/addloc 122001 Gurugram</code> ya <code>/addloc Sector 29 Gurugram</code>")
            return
        if any(l["query"].lower() == query.lower() for l in state["locations"]):
            send(chat_id, "Ye location pehle se list mein hai.")
            return
        loc_id = "loc-" + re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        state["locations"].append({"id": loc_id, "state": "", "label": label, "query": query})
        send(chat_id, f"✅ Location joda: {esc(label)}\nAgle round mein bot Zepto pe '{esc(query)}' search karke pehla address chunega.")

    elif cmd == "/removeloc":
        idx = _pick_index(args, state["locations"])
        if idx is None:
            send(chat_id, "Number bhejein, jaise <code>/removeloc 2</code> (/locs dekhein)")
            return
        removed = state["locations"].pop(idx)
        send(chat_id, f"🗑 Location hataya: {esc(removed['label'])}")

    elif cmd == "/users":
        lines = []
        for uid, info in state["users"].items():
            flag = " ⛔" if info.get("blocked") else ""
            handle = f" @{info['username']}" if info.get("username") else ""
            lines.append(f"<code>{uid}</code> {esc(info.get('name', ''))}{esc(handle)} – pin {info.get('pincode') or '-'}, "
                         f"{len(info.get('products', []))} links{flag}")
        send(chat_id, "👥 Users:\n" + ("\n".join(lines) or "(koi nahi)"))

    elif cmd in ("/block", "/unblock"):
        target = state["users"].get(args.strip())
        if not target:
            send(chat_id, "User ID nahi mila. /users dekhein.")
            return
        target["blocked"] = cmd == "/block"
        send(chat_id, "Done ✅")

    elif cmd == "/setlimit":
        if not args.strip().isdigit():
            send(chat_id, "Format: <code>/setlimit 5</code>")
            return
        state["settings"]["user_link_limit"] = int(args.strip())
        send(chat_id, f"✅ Har user ab {int(args.strip())} links tak add kar sakta hai.")

    elif cmd == "/overview":
        lines = []
        for p in state["channel_products"]:
            spots = []
            for loc in state["locations"]:
                st = state["status"].get(f"{p['pvid']}|{loc['id']}")
                if st and st.get("in_stock"):
                    spots.append(f"{loc['label']}" + (f" ({st['qty']})" if st.get("qty") else ""))
            lines.append(f"• <b>{esc(p.get('name') or 'Zepto product')}</b>: " + (esc(", ".join(spots)) if spots else "kahin stock nahi"))
        send(chat_id, "\n".join(lines) or "Channel list khaali hai.")

    else:
        send(chat_id, "Ye command samajh nahi aaya. /help dekhein.")


def process_updates(state: dict) -> int:
    """Fetch pending Telegram messages and handle them. Returns how many were handled."""
    handled = 0
    while True:
        updates = tg.get_updates(state.get("update_offset", 0))
        if not updates:
            return handled
        for upd in updates:
            state["update_offset"] = upd["update_id"] + 1
            try:
                handle_update(state, upd)
            except Exception as exc:
                print(f"[bot] error handling update {upd.get('update_id')}: {exc}")
            handled += 1

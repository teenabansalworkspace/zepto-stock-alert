"""Zepto stock alert – entry point.

  python main.py once     -> one round: read bot messages, check Zepto, send alerts (used by GitHub Actions)
  python main.py loop     -> keep running on your laptop, one round every CHECK_EVERY_MINUTES
  python main.py genkey   -> make a new STATE_KEY (for encrypted data)
  python main.py test-telegram -> send a test message to the admins and the channel
  python main.py reset-locations -> use the location list from data/locations.json again
  python main.py debug [pincode] -> try one location + one product, save screenshots in debug/
"""
import os
import sys
import time

import bot_commands
import config
import runner
import storage
import telegram_api as tg


def one_round() -> None:
    state = storage.load()
    try:
        n = bot_commands.process_updates(state)
        print(f"[main] {n} Telegram messages handled")
        storage.save(state)  # save early so commands are not lost if the check crashes

        from zepto import ZeptoChecker
        checker = ZeptoChecker()
        try:
            summary = runner.run_checks(state, checker)
        finally:
            checker.close()
        print(f"[main] summary: {summary}")

        n = bot_commands.process_updates(state)  # answer anything that came in during the check
        if n:
            print(f"[main] {n} more Telegram messages handled")
    finally:
        changed = storage.save(state)
        print(f"[main] data saved (changed={changed})")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    if os.environ.get("GITHUB_ACTIONS") == "true" and not config.STATE_KEY and mode != "genkey":
        sys.exit("STATE_KEY secret missing: public repo mein data bina encryption ke save nahi karenge.")
    if mode == "genkey":
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    elif mode == "test-telegram":
        state = storage.load()
        bot_commands.process_updates(state)
        storage.save(state)
        for admin in config.ADMIN_IDS:
            print("admin", admin, tg.send(admin, "✅ Test message: bot chal raha hai."))
        channel = config.CHANNEL_ID or state.get("channel_id")
        if channel:
            print("channel", channel, tg.send(channel, "✅ Test message: channel connected."))
        else:
            print("channel set nahi hai abhi")
    elif mode == "reset-locations":
        # Replace the saved channel locations with data/locations.json (products and users stay as they are)
        state = storage.load()
        state["locations"] = storage._default_state()["locations"]
        keep = {loc["id"] for loc in state["locations"]}
        state["status"] = {k: v for k, v in state["status"].items()
                           if k.split("|", 1)[1] in keep or k.split("|", 1)[1].startswith("pin:")}
        state["rotation"] = 0
        storage.save(state)
        for loc in state["locations"]:
            print(f"  {loc['label']} ({loc['query']})")
        print(f"[main] {len(state['locations'])} locations set.")
    elif mode == "debug":
        # One location + one product, with screenshots in the debug folder
        from zepto import ZeptoChecker, extract_pvid
        pin = sys.argv[2] if len(sys.argv) > 2 else "201301"
        state = storage.load()
        checker = ZeptoChecker()
        try:
            ctx, page, info = checker.open_location(pin)
            print(f"[debug] location {pin}: {info}")
            checker.save_debug(page, f"after_location_{pin}")
            if state["channel_products"]:
                p = state["channel_products"][0]
                print(f"[debug] product: {checker.check_product(page, p['url'], extract_pvid(p['url']))}")
                checker.save_debug(page, "product_page")
        except Exception as exc:
            print(f"[debug] FAILED: {str(exc).splitlines()[0]}")
        finally:
            checker.close()
    elif mode == "loop":
        while True:
            try:
                one_round()
            except Exception as exc:
                print(f"[main] round failed: {exc}")
            print(f"[main] agla round {config.LOCAL_LOOP_MINUTES} minute baad...")
            time.sleep(config.LOCAL_LOOP_MINUTES * 60)
    else:
        one_round()


if __name__ == "__main__":
    main()

"""Owner CLI: python -m app.cli set-password"""
import getpass
import re
import sys
from pathlib import Path

from . import auth
from .config import BACKEND_DIR


def set_password() -> None:
    pw = getpass.getpass("New owner password (min 10 chars): ")
    if len(pw) < 10:
        sys.exit("Too short. Use at least 10 characters.")
    if pw != getpass.getpass("Repeat: "):
        sys.exit("Passwords do not match.")
    hashed = auth.hash_password(pw)
    env_path = BACKEND_DIR / ".env"
    text = env_path.read_text() if env_path.exists() else ""
    if re.search(r"^APP_PASSWORD_HASH=.*$", text, flags=re.M):
        text = re.sub(r"^APP_PASSWORD_HASH=.*$", f"APP_PASSWORD_HASH={hashed}", text, flags=re.M)
    else:
        text += f"\nAPP_PASSWORD_HASH={hashed}\n"
    env_path.write_text(text)
    print(f"Password hash written to {env_path}")


def get_chat_id() -> None:
    """After messaging your bot once on Telegram, this prints your chat id."""
    import json
    import urllib.request

    from . import config
    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("Set TELEGRAM_BOT_TOKEN in backend/.env first (get it from @BotFather).")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.load(resp)
    chats = {str(u["message"]["chat"]["id"]): u["message"]["chat"].get("first_name", "?")
             for u in data.get("result", []) if "message" in u}
    if not chats:
        sys.exit("No messages found. Open Telegram, send your bot any message, then rerun.")
    for cid, name in chats.items():
        print(f"TELEGRAM_CHAT_ID={cid}   (from chat with {name})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "set-password":
        set_password()
    elif cmd == "get-chat-id":
        get_chat_id()
    else:
        print("Usage: python -m app.cli [set-password|get-chat-id]")

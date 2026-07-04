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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "set-password":
        set_password()
    else:
        print("Usage: python -m app.cli set-password")

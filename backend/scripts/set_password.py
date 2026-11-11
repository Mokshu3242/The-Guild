"""Set a new password for a Supabase user (one-off, do not commit).

From the backend folder:  python -m scripts.set_password maya@guild.test
It asks for the new password without showing it on screen.
"""
from dotenv import load_dotenv

load_dotenv()

import getpass  # noqa: E402
import sys  # noqa: E402

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

email = sys.argv[1] if len(sys.argv) > 1 else "maya@guild.test"
headers = {
    "apikey": settings.supabase_secret_key,
    "Authorization": f"Bearer {settings.supabase_secret_key}",
}
base = f"{settings.supabase_url}/auth/v1/admin/users"

r = httpx.get(base, headers=headers, params={"per_page": 1000}, timeout=30)
r.raise_for_status()
user = next((u for u in r.json()["users"] if u["email"] == email), None)
if not user:
    sys.exit(f"No user found with email {email}")

pw = getpass.getpass(f"New password for {email}: ")
if len(pw) < 8 or pw != getpass.getpass("Type it again: "):
    sys.exit("Passwords did not match, or shorter than 8 characters. Nothing changed.")

r = httpx.put(f"{base}/{user['id']}", headers=headers, json={"password": pw}, timeout=30)
print("Done. Password changed." if r.status_code == 200 else f"Failed: HTTP {r.status_code} {r.text}")

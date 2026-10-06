from dotenv import load_dotenv
load_dotenv()

import os
import sys

import httpx

from app.config import settings

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.get_token <email> <password>")
        sys.exit(1)

    email, password = sys.argv[1], sys.argv[2]
    r = httpx.post(
        f"{settings.supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"]},
        json={"email": email, "password": password},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Login failed: HTTP {r.status_code}")
        print(r.text)
        sys.exit(1)
    print(r.json()["access_token"])
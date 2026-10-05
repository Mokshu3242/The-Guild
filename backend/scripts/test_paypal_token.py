# The Guild\backend\scripts\test_paypal_token.py
from dotenv import load_dotenv
load_dotenv()

from app.services.paypal import get_access_token, _base

if __name__ == "__main__":
    token = get_access_token()
    print(f"Base URL: {_base()}")
    print(f"Token: {token[:40]}...")
    print(f"Token length: {len(token)}")
    print("OK — PayPal token works")
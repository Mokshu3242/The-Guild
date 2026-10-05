# The Guild\backend\app\config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PayPal
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"

    # Cloudflare Workers AI
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_ai_model: str = "@cf/meta/llama-3.1-8b-instruct"

    # Supabase
    supabase_url: str = ""
    supabase_secret_key: str = ""
    supabase_jwks_url: str = ""
    database_url: str = ""

    # App
    frontend_url: str = ""


settings = Settings()
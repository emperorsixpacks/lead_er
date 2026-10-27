from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://leads:leads@localhost:5432/leads"
    api_secret: str = "change-me"

    # Tracking
    tracking_base_url: str = "https://t.yourdomain.com"
    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""

    # Discover
    google_maps_api_key: str = ""
    target_categories: str = ""
    target_cities: str = ""
    target_country: str = "US"

    # Verify / Personalize
    millionverifier_api_key: str = ""
    # Local testing: return deterministic results instead of calling a provider.
    email_verify_mock: bool = False
    # Free search API (2k/mo) — better than scraping DuckDuckGo.
    brave_search_api_key: str = ""
    # Tavily search API (1k/mo free) — clean results, plain API key.
    tavily_api_key: str = ""
    # Google Custom Search JSON API (100/day free).
    google_cse_key: str = ""
    google_cse_cx: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Sending (Gmail: SMTP app password, or OAuth API for PaaS like Render)
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 465
    gmail_smtp_user: str = ""
    gmail_smtp_password: str = ""
    # Gmail API (OAuth) — used automatically when gmail_refresh_token is set.
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    daily_send_cap: int = 30
    # BCC a copy of every send to this address (e.g. your own inbox).
    send_bcc_email: str = ""
    # Where to email the draft PDF (for manual sending). Falls back to send_bcc_email.
    report_email: str = ""
    # Email copy: signoff name, pitch, and links (all optional; omitted when empty).
    sender_name: str = ""
    email_value_prop: str = ""
    email_demo_url: str = ""
    email_booking_url: str = ""
    email_linkedin_url: str = ""
    # One-line call-to-action appended after the personalized hook.
    email_cta: str = "Would you be open to a quick 15-minute chat?"
    # Include an unsubscribe link in the footer (recommended for CAN-SPAM/GDPR).
    email_include_unsubscribe: bool = False
    # Include the 1px open-tracking pixel. Off by default: it's a spam signal
    # and open data is noisy; click tracking (wrapped links) stays on.
    email_include_pixel: bool = False
    # CAN-SPAM: physical mailing address + sender name on every email.
    sender_company: str = ""
    sender_address: str = ""

    @property
    def categories(self) -> list[str]:
        return [c.strip() for c in self.target_categories.split(",") if c.strip()]

    @property
    def cities(self) -> list[str]:
        return [c.strip() for c in self.target_cities.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

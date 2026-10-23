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
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Sending (Gmail SMTP via app password)
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 465
    gmail_smtp_user: str = ""
    gmail_smtp_password: str = ""
    daily_send_cap: int = 30
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

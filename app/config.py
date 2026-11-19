"""Application configuration.

All secrets are loaded from environment variables / .env and are never
hardcoded. Secret values are wrapped in ``SecretStr`` so that an accidental
``repr()``/log call prints ``**********`` instead of the real value.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from pydantic import Field, SecretStr, field_validator

if TYPE_CHECKING:
    from app.services.pricing.policy import PricingPolicy
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Telegram ---
    telegram_bot_token: SecretStr

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./amigozt.db"

    # --- AI ---
    openai_api_key: SecretStr | None = None
    #: Image model used for photorealistic build renders.
    image_model: str = "gpt-image-1"
    #: Master switch. Needs OPENAI_API_KEY as well to actually render.
    ai_visualization_enabled: bool = True
    #: gpt-image-1 output: "1024x1024", "1536x1024" or "1024x1536".
    ai_image_size: str = "1024x1024"
    #: "low" / "medium" / "high" - the main cost lever per render.
    ai_image_quality: str = "medium"
    ai_image_timeout_seconds: int = Field(default=90, ge=10, le=600)
    #: Paid attempts per fingerprint before the visualiser stops trying.
    ai_image_max_attempts: int = Field(default=2, ge=1, le=5)
    #: Pass real product photos (catalogue image_url, verified) to the image
    #: model as references. Off by default: enable only for images the shop
    #: is licensed to reuse (manufacturer press kits, an authorised feed).
    ai_reference_images_enabled: bool = False
    #: Approximate price of one image call, for the admin spend counter (USD).
    #: What one render really costs, used for every estimate and ceiling.
    #: gpt-image-1 at medium quality, 1024x1024, bills about $0.042 - the
    #: $0.04 we used before under-counted by 5%, which is how a run that
    #: our ledger said was inside budget still exhausted the account.
    ai_image_cost_usd: Decimal = Field(default=Decimal("0.042"), ge=0)
    #: Generate a product's visual the first time a customer opens its card.
    #: Off by default: product visuals come from the batch generator.
    visual_on_demand_components: bool = False

    # --- Admin ---
    # Stored as a raw string so that a plain comma-separated .env value works.
    admin_telegram_ids: str = ""

    # --- Branding ---
    #: The official AmigoZT PC brand image (path relative to the project root
    #: or absolute). Shown on the welcome screen, the configurator start and
    #: the order confirmation. Replace the file or point this elsewhere to
    #: rebrand without touching bot logic.
    brand_image: str = "app/assets/brand/amigozt_pc.png"
    #: Telegram file_id of the already-uploaded brand image. Optional: the bot
    #: learns and caches the id after its first upload anyway.
    brand_image_file_id: str | None = None
    #: Optional per-purpose assets; each falls back to BRAND_IMAGE when empty.
    brand_avatar: str | None = None
    brand_header: str | None = None
    brand_build_default: str | None = None
    brand_order_confirmation: str | None = None
    #: The same asset is not re-sent to the same chat within this window.
    brand_resend_cooldown_minutes: int = Field(default=30, ge=0)

    # --- Business ---
    #: What an hour of the owner's time should earn. The price is built from
    #: estimated hours x this rate, not from a flat assembly fee.
    target_hourly_earnings_pln: Decimal = Field(default=Decimal(150), gt=0)
    #: Floors: whichever binds harder wins.
    minimum_profit_per_order_pln: Decimal = Field(default=Decimal(500), ge=0)
    minimum_profit_per_hour_pln: Decimal = Field(default=Decimal(100), ge=0)
    #: Prices are rounded up to end in (step - 1): 6 562 -> 6 599.
    price_rounding_step_pln: int = Field(default=100, gt=0)

    # --- Runtime ---
    environment: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"
    #: Discard updates Telegram queued while the bot was offline.
    #:
    #: True (the default) protects against stale callback queries: a tap on a
    #: keyboard that has since changed would reach the wrong handler. Set it
    #: to false after planned downtime to answer the messages customers sent
    #: meanwhile - a ``/start`` nobody replied to is a lost customer.
    drop_pending_updates: bool = True
    default_language: str = "ru"
    rate_limit_per_second: float = Field(default=1.5, gt=0)

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def admin_ids(self) -> frozenset[int]:
        """Parsed set of admin Telegram IDs."""
        ids: set[int] = set()
        for chunk in self.admin_telegram_ids.replace(";", ",").split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                ids.add(int(chunk))
        return frozenset(ids)

    def pricing_policy(self) -> PricingPolicy:
        """Commercial rules assembled from the environment."""
        from app.services.pricing.policy import PricingPolicy

        return PricingPolicy(
            target_hourly_earnings_pln=self.target_hourly_earnings_pln,
            minimum_profit_per_order_pln=self.minimum_profit_per_order_pln,
            minimum_profit_per_hour_pln=self.minimum_profit_per_hour_pln,
            rounding_step_pln=self.price_rounding_step_pln,
        )

    @property
    def openai_key(self) -> str | None:
        value = self.openai_api_key.get_secret_value() if self.openai_api_key else ""
        return value.strip() or None

    @property
    def bot_token(self) -> str:
        """Plain token. Only pass this to the Telegram client - never log it."""
        return self.telegram_bot_token.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()

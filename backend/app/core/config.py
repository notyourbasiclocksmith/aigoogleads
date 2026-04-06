from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import List

_INSECURE_JWT_SECRET = "change-me-to-a-random-secret-key"
_INSECURE_ENCRYPTION_KEY = "change-me-generate-fernet-key"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ignite:ignite@localhost:5432/ignite_ads"
    DATABASE_URL_SYNC: str = "postgresql://ignite:ignite@localhost:5432/ignite_ads"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = _INSECURE_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60
    JWT_REFRESH_EXPIRY_DAYS: int = 30

    # Encryption
    ENCRYPTION_KEY: str = _INSECURE_ENCRYPTION_KEY

    # Google Ads
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    GOOGLE_ADS_CLIENT_ID: str = ""
    GOOGLE_ADS_CLIENT_SECRET: str = ""
    GOOGLE_ADS_REDIRECT_URI: str = "http://localhost:8000/api/ads/accounts/oauth/callback"

    # AI Image Generator (SEOpix Flask API)
    IMAGE_GENERATOR_API_URL: str = ""
    IMAGE_GENERATOR_API_KEY: str = ""
    IMAGE_DEFAULT_ENGINE: str = "google"  # google, dalle, stability, flux

    # S3
    S3_ENDPOINT: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "ignite-ads-assets"
    S3_REGION: str = "us-east-1"

    # App
    APP_ENV: str = "development"
    APP_URL: str = "http://localhost:3000"
    API_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Anthropic (Claude)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # S2S Brain API (for Jarvis and external integrations)
    BRAIN_API_KEY: str = ""

    # Meta Ads
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_REDIRECT_URI: str = "http://localhost:8000/api/meta/oauth/callback"

    # V2 — Stripe Billing
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STARTER: str = ""
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_ELITE: str = ""

    # V2 — SERP Provider
    SERP_PROVIDER_KEY: str = ""

    # V2 — Email (SendGrid / Mailgun)
    EMAIL_PROVIDER_KEY: str = ""
    EMAIL_FROM: str = "contact@thekeybot.com"

    # V2 — Slack
    SLACK_DEFAULT_WEBHOOK: str = ""

    # Google REST APIs (PageSpeed Insights, etc.)
    GOOGLE_API_KEY: str = ""

    # Jarvis Brain S2S
    BRAIN_API_KEY: str = ""

    # Ahrefs API (keyword intelligence for campaign pipeline)
    AHREFS_API_KEY: str = ""

    # CallFlux Bridge (cross-platform LSA + call data)
    CALLFLUX_BRIDGE_API_KEY: str = ""
    CALLFLUX_API_URL: str = ""  # e.g. https://callflux-api.onrender.com

    # V2 — GA4 OAuth
    GA4_CLIENT_ID: str = ""
    GA4_CLIENT_SECRET: str = ""
    GA4_REDIRECT_URI: str = "http://localhost:3000/api/auth/ga4/callback"

    # Google Business Profile (GBP) OAuth
    GBP_CLIENT_ID: str = ""
    GBP_CLIENT_SECRET: str = ""
    GBP_REDIRECT_URI: str = "http://localhost:8000/api/gbp/oauth/callback"

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> "Settings":
        if self.APP_ENV != "development":
            errors = []
            if self.JWT_SECRET == _INSECURE_JWT_SECRET:
                errors.append("JWT_SECRET is set to the insecure default value")
            if self.ENCRYPTION_KEY == _INSECURE_ENCRYPTION_KEY:
                errors.append("ENCRYPTION_KEY is set to the insecure default value")
            if errors:
                raise ValueError(
                    f"Insecure default secrets detected in {self.APP_ENV!r} environment: "
                    + "; ".join(errors)
                    + ". Set secure random values via environment variables."
                )
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

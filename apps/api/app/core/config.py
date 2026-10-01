from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    APP_NAME: str = "Farm Platform API"
    ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg://farm:farm@localhost:5432/farmdb"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60

    DEFAULT_CURRENCY: str = "KES"
    DEFAULT_TIMEZONE: str = "Africa/Nairobi"

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Spec §38 QR codes: the URL a scanned code resolves to. The frontend's
    # own dev-server default - a real deployment must override this to its
    # actual public storefront domain, or every QR code printed prior to
    # that change points at the wrong place.
    PUBLIC_SITE_BASE_URL: str = "http://localhost:3000"

    # Rate limiting backend (spec §29 gap: in-memory limiter isn't correct
    # behind >1 API replica). "memory" is the default so existing tests and
    # the single-instance docker-compose keep working with zero setup;
    # "redis" opts into the shared-store limiter using REDIS_URL above.
    RATE_LIMIT_BACKEND: str = "memory"  # memory | redis

    # How many reverse proxies / load balancers sit in front of the API and
    # append to X-Forwarded-For (e.g. 1 behind a single AWS ALB). 0 (default)
    # means "trust only the socket peer" - the previous behaviour. Without
    # this, behind a load balancer EVERY visitor shares the balancer's IP, so
    # per-IP rate limits would throttle the whole site as one client.
    TRUSTED_PROXY_COUNT: int = 0

    # Spec §47 - OpenTelemetry tracing is entirely opt-in: unset (the
    # default) means core/observability.py's setup_tracing() is a no-op and
    # nothing OTel-related is even imported. Set to a real collector's OTLP
    # HTTP endpoint (e.g. "http://otel-collector:4318/v1/traces") to enable it.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    # Email (spec §13/§55) - "mock" (default) needs nothing extra and is
    # what tests use; the mock provider always succeeds without a network
    # call, mirroring PAYMENT_PROVIDER_MODE's mock default. Switch to "smtp"
    # and fill in the fields below to send real email.
    EMAIL_PROVIDER_MODE: str = "mock"  # mock | smtp
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@example-farm.co.ke"
    SMTP_USE_TLS: bool = True

    # Payments (spec §21-22, §49) - never commit real values; see .env.example.
    PAYMENT_PROVIDER_MODE: str = "mock"  # mock | mpesa | stripe (per-request provider is also selectable)
    MOCK_PAYMENT_SECRET: str = "mock-payment-secret-change-me"
    # The mock provider marks orders paid with no real money, so it is
    # controlled explicitly. None (default) = on for development/test ENVs and
    # OFF for any production-like ENV. True = allow, but only honoured when
    # MOCK_PAYMENT_SECRET is a strong, non-placeholder value (see
    # core/security_checks.py). False = always off.
    ALLOW_MOCK_PAYMENTS: bool | None = None

    # Abandoned guest orders hold inventory (animal reserved / crop stock
    # committed). They're auto-cancelled after these windows; 0 disables a rule.
    GUEST_ORDER_TTL_MINUTES: int = 120
    PAYMENT_PENDING_TTL_HOURS: int = 24

    DARAJA_CONSUMER_KEY: str = ""
    DARAJA_CONSUMER_SECRET: str = ""
    DARAJA_SHORTCODE: str = ""
    DARAJA_PASSKEY: str = ""
    DARAJA_CALLBACK_URL: str = ""
    DARAJA_CALLBACK_SHARED_SECRET: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Custom domains for tenant public storefronts (apps/web's /shop/{slug}
    # pages, reachable at a tenant's own domain instead of yours). Empty by
    # default — the whole feature is inert with no token set, same "opt-in,
    # nothing breaks if unconfigured" pattern as OTEL/SMTP/Daraja above.
    # VERCEL_TEAM_ID is only needed if the project lives under a Vercel team
    # rather than a personal account.
    VERCEL_API_TOKEN: str = ""
    VERCEL_PROJECT_ID: str = ""
    VERCEL_TEAM_ID: str = ""

    # Listing-photo storage (commerce/storage.py). "database" (default) keeps
    # photo bytes in Postgres with zero setup; "supabase" stores them in a
    # Supabase Storage bucket and serves them from its CDN. The bucket must
    # exist and be PUBLIC; the service-role key is server-side only.
    STORAGE_BACKEND: str = "database"  # database | supabase
    SUPABASE_URL: str = ""             # e.g. https://<project-ref>.supabase.co
    SUPABASE_SECRET_KEY: str = ""            # sb_secret_... (Settings > API Keys) - preferred
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "listing-images"


@lru_cache
def get_settings() -> Settings:
    return Settings()

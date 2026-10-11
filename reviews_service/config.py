from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from the environment (/etc/egematch/reviews-*.env on the server, mode 600). Nothing here is committed."""
    database_url: str = "sqlite+aiosqlite:///./reviews-dev.db"
    # HMAC key for emails, IPs, tokens and codes. Losing it makes old hashes unmatchable; leaking it lets someone
    # test guessed emails against the hashes, so it lives only in the server env file.
    hmac_secret: str = ""
    proof_dir: str = "/var/lib/egematch/proofs"
    allowed_origins: str = "https://egematch.ru,https://www.egematch.ru"
    public_port: int = 8085
    admin_port: int = 8090
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    admin_notify_email: str = ""
    # Leads (requests to schools). The master switch lives in the database (site_flags) and is flipped in the console.
    leads_port: int = 8081
    operator_name: str = "Стародубцев Александр Дмитриевич"
    operator_contact: str = "info@egematch.ru"
    telegram_bot_token: str = ""      # only to post a lead into a school's Telegram group
    telegram_api_base: str = ""       # a relay URL, because api.telegram.org is blocked from Russian servers
    leads_alert_email: str = ""       # where "a lead could not be delivered" goes
    model_config = SettingsConfigDict(env_prefix="REVIEWS_", env_file=None, extra="ignore")

    @property
    def origins(self) -> set:
        return {item.strip() for item in self.allowed_origins.split(",") if item.strip()}

    def check(self):
        if len(self.hmac_secret) < 32:
            raise SystemExit("REVIEWS_HMAC_SECRET must be at least 32 characters.")

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str = "sqlite+aiosqlite:///./egeshka.db"
    admin_ids: str = ""
    channel_url: str = "https://t.me/EgeMatch_blog"
    operator_name: str = "владелец сервиса ЕГЭ Мэтч"
    operator_contact: str = ""
    # Site leads ("Выбрать школу" -> request to a school). Off until the legal texts, the RF server and
    # a signed agreement with a school exist; each school is switched on separately in lead_schools.
    leads_enabled: bool = False
    leads_port: int = 8081
    leads_allowed_origins: str = "https://egematch.ru,https://www.egematch.ru"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip().isdigit()}

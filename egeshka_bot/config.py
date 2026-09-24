from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str = "sqlite+aiosqlite:///./egeshka.db"
    admin_ids: str = ""
    channel_url: str = "https://t.me/EgeMatch_blog"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip().isdigit()}

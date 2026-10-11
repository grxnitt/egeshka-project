"""Adapts the review service settings to what egeshka_bot.leads expects, and keeps the global switch fresh."""
import asyncio
import logging

from sqlalchemy import text

log = logging.getLogger("reviews.leads")


class LeadSettings:
    """Looks like egeshka_bot.config.Settings for the leads code. `leads_enabled` is read from site_flags by a
    background task, so flipping the switch in the console takes effect within seconds, without a restart."""

    def __init__(self, settings):
        self.smtp_host, self.smtp_port = settings.smtp_host, settings.smtp_port
        self.smtp_user, self.smtp_password = settings.smtp_user, settings.smtp_password
        self.smtp_from = settings.smtp_from or settings.smtp_user
        self.bot_token = settings.telegram_bot_token
        self.telegram_api_base = settings.telegram_api_base
        self.alert_email = settings.leads_alert_email or settings.admin_notify_email
        self.admin_id_set = set()
        self.operator_name = settings.operator_name
        self.operator_contact = settings.operator_contact
        self.leads_allowed_origins = settings.allowed_origins
        self.leads_enabled = False

    async def refresh(self, session_factory) -> bool:
        async with session_factory() as session:
            row = (await session.execute(text("select value from site_flags where key = 'leads_enabled'"))).first()
        self.leads_enabled = bool(row and row[0])
        return self.leads_enabled

    async def keep_fresh(self, session_factory, every: int = 10):
        while True:
            try:
                await self.refresh(session_factory)
            except Exception:  # noqa: BLE001 - on any failure the switch stays as it was (OFF at start)
                log.warning("could not read the leads switch")
            await asyncio.sleep(every)

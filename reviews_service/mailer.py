"""Plain-text mail through the egematch.ru mailbox (Reg.ru, Russia). No links in code letters: nothing to phish with."""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid


class MailError(RuntimeError):
    pass


def _send(settings, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = formataddr(("ЕГЭ Мэтч", settings.smtp_from or settings.smtp_user))
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="egematch.ru")
    message.set_content(body)
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=context) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


def check_login(settings) -> None:
    """Raises if the mailbox cannot be logged in to (used by the console health check; nothing is sent)."""
    if not settings.smtp_host or not settings.smtp_user:
        raise MailError("SMTP is not configured")
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=12, context=context) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=12) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.smtp_user, settings.smtp_password)


async def send(settings, to: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_user:
        raise MailError("SMTP is not configured")
    try:
        await asyncio.to_thread(_send, settings, to, subject, body)
    except Exception as exc:  # noqa: BLE001
        raise MailError(type(exc).__name__) from None


def review_code_letter(code: str) -> tuple:
    return ("Код подтверждения отзыва — ЕГЭ Мэтч",
            f"Код для подтверждения отзыва на egematch.ru: {code}\n\n"
            "Он действует 15 минут. Введи его на странице отзыва.\n\n"
            "Если ты не оставлял отзыв, просто проигнорируй это письмо: без кода отзыв не будет сохранён.\n\n"
            "ЕГЭ Мэтч\n")


def deletion_code_letter(code: str) -> tuple:
    return ("Код для удаления данных — ЕГЭ Мэтч",
            f"Код для удаления твоих данных с egematch.ru: {code}\n\n"
            "Он действует 15 минут. После ввода кода мы удалим все отзывы, оставленные с этой почты, и связанные с ними данные.\n\n"
            "Если ты не запрашивал удаление, проигнорируй письмо: без кода ничего не произойдёт.\n\n"
            "ЕГЭ Мэтч\n")


def moderation_letter(count: int) -> tuple:
    return ("Новые отзывы на модерации — ЕГЭ Мэтч",
            f"В очереди модерации отзывов: {count}.\n\nОткрой админку через SSH-туннель (scripts/admin.sh).\n")

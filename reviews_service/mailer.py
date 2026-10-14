"""Plain-text mail through the egematch.ru mailbox (Reg.ru, Russia). No links in code letters: nothing to phish with."""
import asyncio
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape


class MailError(RuntimeError):
    pass


# The Reg.ru mail server now and then drops a connection at login even though the password is right. Dropped
# connections and timeouts are tried again (a wrong password or a refused recipient is not: that never gets better).
TRANSIENT = (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, TimeoutError, ConnectionError, ssl.SSLError)
ATTEMPTS = 3


def _retrying(action):
    for attempt in range(ATTEMPTS):
        try:
            return action()
        except TRANSIENT:
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def _send(settings, to: str, subject: str, body: str) -> None:
    _retrying(lambda: _send_once(settings, to, subject, body))


def _send_once(settings, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = formataddr(("ЕГЭ Мэтч", settings.smtp_from or settings.smtp_user))
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="egematch.ru")
    message["Date"] = formatdate(localtime=True)
    message["Reply-To"] = settings.smtp_from or settings.smtp_user
    # a machine-sent one-off letter: tells autoresponders to stay quiet, and spam filters that nobody is being mailed in bulk
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "All"
    message.set_content(body)
    message.add_alternative(_html(body), subtype="html")      # text and HTML versions, as the big senders do
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


def _html(body: str) -> str:
    """The same text as a plain HTML letter: no images, no links, no scripts."""
    paragraphs = "".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in body.strip().split("\n\n"))
    return f'<html><body style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#222">{paragraphs}</body></html>'


def check_login(settings) -> None:
    """Raises if the mailbox cannot be logged in to (used by the console health check; nothing is sent)."""
    if not settings.smtp_host or not settings.smtp_user:
        raise MailError("SMTP is not configured")
    _retrying(lambda: _check_login_once(settings))


def _check_login_once(settings) -> None:
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
    return (f"Код подтверждения: {code} — ЕГЭ Мэтч",
            f"Код для подтверждения отзыва на egematch.ru: {code}\n\n"
            "Он действует 15 минут. Введи его на странице отзыва.\n\n"
            "Если ты не оставлял отзыв, просто проигнорируй это письмо: без кода отзыв не будет сохранён.\n\n"
            "ЕГЭ Мэтч, egematch.ru\n")


def deletion_code_letter(code: str) -> tuple:
    return (f"Код удаления данных: {code} — ЕГЭ Мэтч",
            f"Код для удаления твоих данных с egematch.ru: {code}\n\n"
            "Он действует 15 минут. После ввода кода мы удалим все отзывы, оставленные с этой почты, и связанные с ними данные.\n\n"
            "Если ты не запрашивал удаление, проигнорируй письмо: без кода ничего не произойдёт.\n\n"
            "ЕГЭ Мэтч, egematch.ru\n")


def moderation_letter(count: int) -> tuple:
    return ("Новые отзывы на модерации — ЕГЭ Мэтч",
            f"В очереди модерации отзывов: {count}.\n\nОткрой админку через SSH-туннель (scripts/admin.sh).\n")

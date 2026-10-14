import smtplib
from types import SimpleNamespace

import pytest

from reviews_service import mailer

SETTINGS = SimpleNamespace(smtp_host="mail.example", smtp_port=465, smtp_user="a@b.ru", smtp_password="x", smtp_from="a@b.ru")


class FakeSMTP:
    """A mail server that drops the first `drops` connections at login."""
    calls = 0
    drops = 0
    sent = []

    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *exc): return False

    def login(self, user, password):
        FakeSMTP.calls += 1
        if FakeSMTP.calls <= FakeSMTP.drops:
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    def send_message(self, message): FakeSMTP.sent.append(message["To"])


@pytest.fixture(autouse=True)
def fake_server(monkeypatch):
    FakeSMTP.calls, FakeSMTP.drops, FakeSMTP.sent = 0, 0, []
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(mailer.time, "sleep", lambda seconds: None)


def test_a_dropped_connection_is_retried_and_the_letter_goes_out():
    FakeSMTP.drops = 2
    mailer._send(SETTINGS, "to@x.ru", "s", "b")
    assert FakeSMTP.calls == 3 and FakeSMTP.sent == ["to@x.ru"]


def test_it_gives_up_after_three_attempts():
    FakeSMTP.drops = 10
    with pytest.raises(smtplib.SMTPServerDisconnected):
        mailer._send(SETTINGS, "to@x.ru", "s", "b")
    assert FakeSMTP.calls == 3 and FakeSMTP.sent == []


def test_a_wrong_password_is_not_retried(monkeypatch):
    def refuse(self, user, password):
        FakeSMTP.calls += 1
        raise smtplib.SMTPAuthenticationError(535, b"bad")
    monkeypatch.setattr(FakeSMTP, "login", refuse)
    with pytest.raises(smtplib.SMTPAuthenticationError):
        mailer._send(SETTINGS, "to@x.ru", "s", "b")
    assert FakeSMTP.calls == 1


def test_the_health_check_retries_too():
    FakeSMTP.drops = 1
    mailer.check_login(SETTINGS)
    assert FakeSMTP.calls == 2


def test_the_code_letter_is_short_machine_marked_and_has_a_text_and_html_part():
    import email
    sent = {}

    class Catch(FakeSMTP):
        def send_message(self, message): sent["m"] = message

    mailer.smtplib.SMTP_SSL = Catch
    subject, body = mailer.review_code_letter("654321")
    mailer._send(SETTINGS, "to@x.ru", subject, body)
    message = sent["m"]
    assert "654321" in message["Subject"] and len(message["Subject"]) < 50
    assert message["Auto-Submitted"] == "auto-generated" and message["Date"] and message["Reply-To"] == "a@b.ru"
    kinds = [part.get_content_type() for part in message.walk() if not part.is_multipart()]
    assert kinds == ["text/plain", "text/html"]
    html = message.get_body(("html",)).get_content()
    assert "<a " not in html and "654321" in html

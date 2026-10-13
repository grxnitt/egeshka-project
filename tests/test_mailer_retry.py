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

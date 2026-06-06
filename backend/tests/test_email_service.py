import pytest

from services.email_service import (
    ConsoleEmailSender,
    build_verify_email,
    build_reset_email,
)


@pytest.mark.asyncio
async def test_console_sender_records():
    sender = ConsoleEmailSender()
    await sender.send(to="a@b.com", subject="Hi", html="<b>x</b>", text="visit https://x/verify?token=abc")
    assert len(sender.sent) == 1
    assert sender.sent[0]["to"] == "a@b.com"
    assert "token=abc" in sender.sent[0]["text"]


def test_build_verify_email_contains_link():
    subject, html, text = build_verify_email("https://inkwild.app/verify-email?token=abc")
    assert subject
    assert "verify-email?token=abc" in html
    assert "verify-email?token=abc" in text


def test_build_reset_email_contains_link():
    subject, html, text = build_reset_email("https://inkwild.app/reset-password?token=xyz")
    assert subject
    assert "reset-password?token=xyz" in html
    assert "reset-password?token=xyz" in text

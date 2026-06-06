"""Transactional email — console (dev) and Resend (prod) backends.

Mirrors the image_storage abstraction: a swappable sender behind a factory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class EmailSender(ABC):
    @abstractmethod
    async def send(self, *, to: str, subject: str, html: str, text: str) -> None: ...


class ConsoleEmailSender(EmailSender):
    """Dev backend — logs the email (incl. link) instead of sending.

    The full body lands in structlog output, so dev smoke tests can read the
    verification/reset link from `docker logs`. Keeps a `sent` list for unit tests.
    """

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text})
        logger.info("email_console", to=to, subject=subject, body=text)


class ResendEmailSender(EmailSender):
    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
            resp.raise_for_status()
        logger.info("email_sent_resend", to=to, subject=subject)


def get_email_sender() -> EmailSender:
    """Factory — returns the configured email backend."""
    if settings.email_backend.lower().strip() == "resend":
        return ResendEmailSender()
    return ConsoleEmailSender()


# Email-safe font stack (clients ignore @font-face; keep system fonts).
_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',"
    "Arial,'PingFang SC','Microsoft YaHei',sans-serif"
)


def _render_html(*, preheader: str, title: str, intro: str, button_label: str, link: str) -> str:
    """Modern transactional email — frameless white surface, centered, airy, lightly-rounded button."""
    return f"""\
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff;margin:0;padding:56px 16px;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:460px;">
      <tr><td align="center" style="padding:0 24px;">
        <span style="font-family:Georgia,'Times New Roman',serif;font-size:24px;font-weight:700;color:#18181b;letter-spacing:0.3px;">InkWild</span>
      </td></tr>
      <tr><td align="center" style="padding:40px 24px 0;">
        <h1 style="margin:0;font-family:{_FONT};font-size:22px;font-weight:600;color:#18181b;">{title}</h1>
      </td></tr>
      <tr><td align="center" style="padding:16px 24px 0;">
        <p style="margin:0;font-family:{_FONT};font-size:15px;line-height:1.75;color:#52525b;">{intro}</p>
      </td></tr>
      <tr><td align="center" style="padding:36px 24px 8px;">
        <table role="presentation" cellpadding="0" cellspacing="0"><tr>
          <td style="border-radius:12px;background-color:#18181b;">
            <a href="{link}" target="_blank" style="display:inline-block;padding:14px 44px;font-family:{_FONT};font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;">{button_label}</a>
          </td>
        </tr></table>
      </td></tr>
      <tr><td align="center" style="padding:36px 24px 0;">
        <p style="margin:0;font-family:{_FONT};font-size:13px;line-height:1.6;color:#a1a1aa;">按钮无法点击？复制下面的链接到浏览器打开</p>
        <p style="margin:8px 0 0;font-family:{_FONT};font-size:13px;line-height:1.6;word-break:break-all;"><a href="{link}" style="color:#71717a;text-decoration:none;">{link}</a></p>
      </td></tr>
      <tr><td align="center" style="padding:48px 24px 0;">
        <p style="margin:0;font-family:{_FONT};font-size:12px;line-height:1.7;color:#c4c4cc;">如非本人操作，忽略本邮件即可<br>InkWild · AI 驱动的互动叙事</p>
      </td></tr>
    </table>
  </td></tr>
</table>"""


def build_verify_email(link: str) -> tuple[str, str, str]:
    subject = "验证你的 InkWild 邮箱"
    text = (
        "欢迎来到 InkWild！\n\n"
        f"点击链接完成邮箱验证（24 小时内有效）：\n{link}\n\n"
        "如非本人操作，忽略本邮件即可。"
    )
    html = _render_html(
        preheader="完成邮箱验证，开始你的 InkWild 之旅",
        title="验证你的邮箱",
        intro="欢迎来到 InkWild。点下面的按钮完成邮箱验证即可登录，链接 24 小时内有效。",
        button_label="验证邮箱",
        link=link,
    )
    return subject, html, text


def build_reset_email(link: str) -> tuple[str, str, str]:
    subject = "重置你的 InkWild 密码"
    text = (
        "我们收到了重置你 InkWild 密码的请求。\n\n"
        f"点击链接设置新密码（1 小时内有效）：\n{link}\n\n"
        "如非本人操作，忽略本邮件即可。"
    )
    html = _render_html(
        preheader="重置你的 InkWild 密码",
        title="重置你的密码",
        intro="我们收到了重置你 InkWild 密码的请求。点下面的按钮设置新密码，链接 1 小时内有效。",
        button_label="重置密码",
        link=link,
    )
    return subject, html, text

"""
Convenience functions for other projects to call DingTalk directly (no HTTP server needed).

Usage:
    from dingtalk_webhook.client import send_text, send_markdown

    send_text("Hello world")
    send_markdown("Title", "# Hello\nContent")
"""

from .sender import DingTalkSender

_sender = None


def _get_sender():
    global _sender
    if _sender is None:
        from .sender import DingTalkSender
        import os

        token = os.environ.get(
            "DINGTALK_ACCESS_TOKEN",
            "9f2bd3f1fcff3c673de165149be67895980b69001db1096f6eb0da329070cb2c",
        )
        secret = os.environ.get(
            "DINGTALK_SECRET",
            "SEC534c62399a9f81870bde8558d8c9a74592c1020c93c9ac13054e49bd4e62943b",
        )
        _sender = DingTalkSender(token, secret)
    return _sender


def send_text(content: str, at_mobiles: list[str] | None = None, at_all: bool = False) -> dict:
    return _get_sender().send_text(content, at_mobiles, at_all)


def send_markdown(title: str, text: str, at_mobiles: list[str] | None = None, at_all: bool = False) -> dict:
    return _get_sender().send_markdown(title, text, at_mobiles, at_all)


def send_link(title: str, text: str, message_url: str, pic_url: str = "") -> dict:
    return _get_sender().send_link(title, text, message_url, pic_url)


def notify(sender: str, content: str) -> dict:
    """Send a formatted notification with sender, timestamp, and content."""
    from datetime import datetime
    now = datetime.now().strftime("%H:%M:%S")
    formatted = f"发送者: {sender}\n时间: {now}\n内容: {content}"
    return _get_sender().send_text(formatted)

"""Message formatting and delivery."""

import html
import logging
from typing import Protocol

import httpx

from palavra_do_dia.errors import NotificationError
from palavra_do_dia.models import Passage

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_MAX_FAILURE_DETAIL = 300


class Notifier(Protocol):
    def send(self, text: str) -> None:
        """Deliver an HTML-formatted message."""
        ...


def format_passage(passage: Passage) -> str:
    """Render a passage as Telegram-flavoured HTML."""
    multiple = len(passage.verses) > 1
    body = " ".join(
        (f"{str(verse.number).translate(_SUPERSCRIPT)} " if multiple else "")
        + html.escape(verse.text, quote=False)
        for verse in passage.verses
    )
    label = html.escape(passage.reference.label, quote=False)
    return (
        "📖 <b>Palavra do Dia</b>\n\n"
        f"<blockquote>{body}</blockquote>\n\n"
        f"<b>{label}</b> · {html.escape(passage.version, quote=False)}"
    )


def format_failure(error: BaseException) -> str:
    """Render an operational alert. The detail is truncated and escaped."""
    detail = html.escape(f"{type(error).__name__}: {error}"[:_MAX_FAILURE_DETAIL], quote=False)
    return f"⚠️ <b>Palavra do Dia falhou hoje.</b>\n\n<code>{detail}</code>"


class TelegramNotifier:
    """Sends messages through the Telegram Bot API."""

    def __init__(
        self, token: str, chat_id: str, *, client: httpx.Client | None = None, timeout: float = 15.0
    ) -> None:
        self._url = f"{TELEGRAM_API}/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._client = client or httpx.Client(timeout=timeout)

    def send(self, text: str) -> None:
        # The bot token lives in the URL, so httpx exceptions (which embed it) must never
        # be propagated or logged. Only the status code / exception type are surfaced.
        try:
            response = self._client.post(
                self._url,
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
            )
        except httpx.HTTPError as exc:
            raise NotificationError(f"Telegram unreachable: {type(exc).__name__}") from None
        if response.is_error:
            raise NotificationError(f"Telegram returned HTTP {response.status_code}")

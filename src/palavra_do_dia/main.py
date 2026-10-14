"""Command-line entry point."""

import argparse
import datetime as dt
import logging
import sys
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from palavra_do_dia.bible import (
    AbibliaDigitalProvider,
    BibleService,
    LocalBibleProvider,
)
from palavra_do_dia.config import Settings
from palavra_do_dia.errors import ConfigError, NotificationError
from palavra_do_dia.history import HistoryStore
from palavra_do_dia.notifier import TelegramNotifier, format_failure
from palavra_do_dia.pipeline import DailyWord
from palavra_do_dia.selector import GeminiSelector

logger = logging.getLogger("palavra_do_dia")

TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs full request URLs at INFO, and the Telegram bot token is part of that URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="palavra-do-dia", description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="select and print; do not send or record"
    )
    parser.add_argument(
        "--force", action="store_true", help="deliver even if today's passage was already sent"
    )
    return parser.parse_args(argv)


def _build(settings: Settings) -> tuple[DailyWord, TelegramNotifier]:
    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    bible = BibleService(
        [
            AbibliaDigitalProvider(settings.bible_version),
            LocalBibleProvider(settings.local_bible_path, version=settings.local_bible_version),
        ]
    )
    app = DailyWord(
        selector=GeminiSelector(settings.gemini_api_key, settings.gemini_model),
        bible=bible,
        history=HistoryStore(settings.history_path),
        notifier=notifier,
        history_window=settings.history_window,
        max_attempts=settings.max_attempts,
    )
    return app, notifier


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _configure_logging()

    try:
        settings = Settings.from_env(require_telegram=not args.dry_run)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 2

    app, notifier = _build(settings)
    today = dt.datetime.now(TIMEZONE).date()

    try:
        app.run(today, force=args.force, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - top-level boundary: log, alert, exit non-zero
        logger.exception("Daily run failed")
        if not args.dry_run:
            _alert_failure(notifier, exc)
        return 1
    return 0


def _alert_failure(notifier: TelegramNotifier, error: BaseException) -> None:
    try:
        notifier.send(format_failure(error))
    except NotificationError:
        logger.exception("Could not deliver the failure alert")


if __name__ == "__main__":
    sys.exit(main())

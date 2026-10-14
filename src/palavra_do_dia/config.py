"""Environment-based configuration."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from palavra_do_dia.errors import ConfigError


@dataclass(frozen=True, slots=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    telegram_bot_token: str
    telegram_chat_id: str
    bible_version: str
    history_path: Path
    local_bible_path: Path
    local_bible_version: str
    history_window: int
    max_attempts: int

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, *, require_telegram: bool = True
    ) -> "Settings":
        """Build settings from environment variables, reporting every missing one at once."""
        source = os.environ if env is None else env

        required = ["GEMINI_API_KEY", "GEMINI_MODEL"]
        if require_telegram:
            required += ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
        missing = [name for name in required if not source.get(name, "").strip()]
        if missing:
            raise ConfigError(f"missing environment variables: {', '.join(missing)}")

        return cls(
            gemini_api_key=source["GEMINI_API_KEY"].strip(),
            gemini_model=source["GEMINI_MODEL"].strip(),
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=source.get("TELEGRAM_CHAT_ID", "").strip(),
            bible_version=source.get("BIBLE_VERSION", "nvi").strip().lower(),
            history_path=Path(source.get("HISTORY_PATH", "data/history.json")),
            local_bible_path=Path(source.get("LOCAL_BIBLE_PATH", "data/almeida1911.json")),
            local_bible_version=source.get("LOCAL_BIBLE_VERSION", "ALM1911").strip(),
            history_window=_positive_int(source, "HISTORY_WINDOW", 60),
            max_attempts=_positive_int(source, "MAX_SELECTION_ATTEMPTS", 3),
        )


def _positive_int(source: Mapping[str, str], name: str, default: int) -> int:
    raw = source.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ConfigError(f"{name} must be >= 1, got {value}")
    return value

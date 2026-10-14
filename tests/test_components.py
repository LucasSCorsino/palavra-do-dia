import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx
from google.genai import errors as genai_errors

from palavra_do_dia.config import Settings
from palavra_do_dia.errors import (
    ConfigError,
    InvalidReferenceError,
    NotificationError,
    SelectionError,
)
from palavra_do_dia.history import HistoryStore
from palavra_do_dia.models import Passage, Verse
from palavra_do_dia.notifier import TelegramNotifier, format_failure, format_passage
from palavra_do_dia.selector import GeminiSelector, PassageChoice, build_prompt
from tests.conftest import make_entry, make_ref

# --- selector ----------------------------------------------------------------------------


class _FakeModels:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.kwargs: dict[str, object] = {}

    def generate_content(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _selector(outcome: object) -> tuple[GeminiSelector, _FakeModels]:
    models = _FakeModels(outcome)
    return GeminiSelector("key", "some-model", client=SimpleNamespace(models=models)), models


def test_selector_returns_validated_reference_from_parsed_response() -> None:
    parsed = PassageChoice(book="SL", chapter=23, verse_start=1, verse_end=3)
    selector, models = _selector(SimpleNamespace(parsed=parsed, text=None))

    reference = selector.choose([], "Profetas maiores", [])

    assert reference.label == "Salmos 23:1-3"
    assert models.kwargs["model"] == "some-model"


def test_selector_falls_back_to_text_json() -> None:
    text = '{"book": "jo", "chapter": 1, "verse_start": 1, "verse_end": 5}'
    selector, _ = _selector(SimpleNamespace(parsed=None, text=text))

    assert selector.choose([], "g", []).label == "João 1:1-5"


def test_selector_unparsable_response_is_selection_error() -> None:
    selector, _ = _selector(SimpleNamespace(parsed=None, text="not json"))

    with pytest.raises(SelectionError):
        selector.choose([], "g", [])


def test_selector_invalid_reference_is_retryable_error() -> None:
    parsed = PassageChoice(book="xx", chapter=1, verse_start=1, verse_end=1)
    selector, _ = _selector(SimpleNamespace(parsed=parsed, text=None))

    with pytest.raises(InvalidReferenceError):
        selector.choose([], "g", [])


def test_selector_wraps_api_errors() -> None:
    error = genai_errors.ServerError(503, {"error": {"message": "overloaded"}})
    selector, _ = _selector(error)

    with pytest.raises(SelectionError):
        selector.choose([], "g", [])


def test_prompt_contains_history_group_catalog_and_rejections() -> None:
    prompt = build_prompt([make_entry(make_ref())], "Profetas menores", ["Salmos 1:1 was used"])

    assert "João 3:16-17" in prompt
    assert "Profetas menores" in prompt
    assert "gn=Gênesis" in prompt
    assert "Salmos 1:1 was used" in prompt
    assert "Não escreva o texto bíblico" in prompt


# --- notifier ----------------------------------------------------------------------------


def _passage(*texts: str) -> Passage:
    return Passage(
        reference=make_ref(start=16, end=15 + len(texts)),
        verses=[Verse(number=16 + i, text=text) for i, text in enumerate(texts)],
        version="NVI",
    )


def test_format_single_verse_has_no_verse_numbers() -> None:
    message = format_passage(_passage("Deus amou o mundo"))

    assert "<blockquote>Deus amou o mundo</blockquote>" in message
    assert "<b>João 3:16</b> · NVI" in message


def test_format_multiple_verses_uses_superscript_numbers() -> None:
    message = format_passage(_passage("um", "dois"))

    assert "¹⁶ um ¹⁷ dois" in message


def test_format_escapes_html() -> None:
    assert "&lt;b&gt;" in format_passage(_passage("<b>x</b>"))


def test_format_failure_truncates_and_escapes() -> None:
    message = format_failure(RuntimeError("<" + "x" * 1000))

    assert "&lt;" in message
    assert len(message) < 500


@respx.mock
def test_telegram_sends_html_message() -> None:
    route = respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    TelegramNotifier("TOKEN", "42", client=httpx.Client()).send("hi")

    assert route.called
    body = route.calls.last.request.content.decode()
    assert '"chat_id":"42"' in body.replace(" ", "")
    assert "HTML" in body


@respx.mock
def test_telegram_http_error_does_not_leak_token() -> None:
    respx.post("https://api.telegram.org/botSECRET/sendMessage").mock(
        return_value=httpx.Response(401)
    )

    with pytest.raises(NotificationError) as info:
        TelegramNotifier("SECRET", "42", client=httpx.Client()).send("hi")

    assert "SECRET" not in str(info.value)


@respx.mock
def test_telegram_network_error_does_not_leak_token() -> None:
    respx.post("https://api.telegram.org/botSECRET/sendMessage").mock(
        side_effect=httpx.ConnectError("boom https://api.telegram.org/botSECRET/sendMessage")
    )

    with pytest.raises(NotificationError) as info:
        TelegramNotifier("SECRET", "42", client=httpx.Client()).send("hi")

    assert "SECRET" not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


# --- history -----------------------------------------------------------------------------


def test_history_missing_file_is_empty(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.json")

    assert store.load() == []
    assert not store.has_entry_for(dt.date(2026, 1, 1))


def test_history_roundtrip_and_queries(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "nested" / "history.json")
    store.append(make_entry(make_ref("jo", 3, 16, 17), dt.date(2026, 1, 1)))
    store.append(make_entry(make_ref("sl", 23, 1, 3), dt.date(2026, 1, 2)))

    assert [entry.reference.book for entry in store.load()] == ["jo", "sl"]
    assert [entry.reference.book for entry in store.recent(1)] == ["sl"]
    assert store.recent(0) == []
    assert store.has_entry_for(dt.date(2026, 1, 2))
    assert store.was_used(make_ref("jo", 3, 17, 18), window=10)
    assert not store.was_used(make_ref("jo", 3, 17, 18), window=1)  # outside the window


def test_history_corrupt_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(Exception, match="unreadable or corrupt"):
        HistoryStore(path).load()


# --- config ------------------------------------------------------------------------------


def test_config_reports_all_missing_variables() -> None:
    with pytest.raises(ConfigError) as info:
        Settings.from_env({})

    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert name in str(info.value)


def test_config_telegram_optional_for_dry_run() -> None:
    settings = Settings.from_env(
        {"GEMINI_API_KEY": "k", "GEMINI_MODEL": "m"}, require_telegram=False
    )

    assert settings.bible_version == "nvi"
    assert settings.history_window == 60
    assert settings.max_attempts == 3


def test_config_model_has_no_default() -> None:
    with pytest.raises(ConfigError, match="GEMINI_MODEL"):
        Settings.from_env({"GEMINI_API_KEY": "k"}, require_telegram=False)


@pytest.mark.parametrize("value", ["abc", "0", "-3"])
def test_config_rejects_bad_integers(value: str) -> None:
    env = {"GEMINI_API_KEY": "k", "GEMINI_MODEL": "m", "HISTORY_WINDOW": value}

    with pytest.raises(ConfigError, match="HISTORY_WINDOW"):
        Settings.from_env(env, require_telegram=False)

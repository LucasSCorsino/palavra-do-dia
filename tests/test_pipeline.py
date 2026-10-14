import datetime as dt
from pathlib import Path

import pytest

from palavra_do_dia.bible import BibleService
from palavra_do_dia.errors import InvalidReferenceError, NotificationError, SelectionError
from palavra_do_dia.history import HistoryStore
from palavra_do_dia.main import main
from palavra_do_dia.pipeline import DailyWord
from tests.conftest import (
    FakeProvider,
    RecordingNotifier,
    ScriptedSelector,
    make_entry,
    make_ref,
)

TODAY = dt.date(2026, 10, 13)


def _app(
    tmp_path: Path,
    selector: ScriptedSelector,
    notifier: RecordingNotifier | None = None,
    provider: FakeProvider | None = None,
    max_attempts: int = 3,
) -> tuple[DailyWord, HistoryStore, RecordingNotifier]:
    history = HistoryStore(tmp_path / "history.json")
    notifier = notifier or RecordingNotifier()
    app = DailyWord(
        selector=selector,
        bible=BibleService([provider or FakeProvider("NVI")]),
        history=history,
        notifier=notifier,
        max_attempts=max_attempts,
        choose_group=lambda groups: groups[0],
    )
    return app, history, notifier


def test_happy_path_sends_and_records(tmp_path: Path) -> None:
    app, history, notifier = _app(tmp_path, ScriptedSelector([make_ref(start=1, end=2)]))

    passage = app.run(TODAY)

    assert passage is not None
    assert len(notifier.messages) == 1
    assert "verse 1" in notifier.messages[0]
    assert [entry.date for entry in history.load()] == [TODAY]


def test_skips_when_already_delivered_today(tmp_path: Path) -> None:
    selector = ScriptedSelector([])
    app, history, notifier = _app(tmp_path, selector)
    history.append(make_entry(make_ref(), TODAY))

    assert app.run(TODAY) is None
    assert notifier.messages == []
    assert selector.calls == []


def test_force_delivers_again(tmp_path: Path) -> None:
    app, history, notifier = _app(tmp_path, ScriptedSelector([make_ref("sl", 1, 1, 2)]))
    history.append(make_entry(make_ref(), TODAY))

    assert app.run(TODAY, force=True) is not None
    assert len(notifier.messages) == 1


def test_dry_run_neither_sends_nor_records(tmp_path: Path) -> None:
    app, history, notifier = _app(tmp_path, ScriptedSelector([make_ref()]))

    assert app.run(TODAY, dry_run=True) is not None
    assert notifier.messages == []
    assert history.load() == []


def test_retries_after_invalid_reference_and_feeds_back_rejection(tmp_path: Path) -> None:
    selector = ScriptedSelector(
        [InvalidReferenceError("João 99 does not exist"), make_ref(start=1, end=2)]
    )
    app, _, notifier = _app(tmp_path, selector)

    assert app.run(TODAY) is not None
    assert selector.calls[1][2] == ["João 99 does not exist"]
    assert len(notifier.messages) == 1


def test_rejects_recently_used_passage(tmp_path: Path) -> None:
    used = make_ref("jo", 3, 16, 17)
    selector = ScriptedSelector([make_ref("jo", 3, 17, 18), make_ref("sl", 1, 1, 2)])
    app, history, _ = _app(tmp_path, selector)
    history.append(make_entry(used, TODAY - dt.timedelta(days=1)))

    passage = app.run(TODAY)

    assert passage is not None
    assert passage.reference.book == "sl"
    assert len(selector.calls) == 2


def test_out_of_range_verses_trigger_retry(tmp_path: Path) -> None:
    selector = ScriptedSelector([make_ref(start=39, end=43), make_ref(start=1, end=2)])
    app, _, _ = _app(tmp_path, selector)

    passage = app.run(TODAY)

    assert passage is not None
    assert passage.reference.verse_start == 1


def test_gives_up_after_max_attempts(tmp_path: Path) -> None:
    selector = ScriptedSelector([InvalidReferenceError("bad")] * 2)
    app, history, notifier = _app(tmp_path, selector, max_attempts=2)

    with pytest.raises(SelectionError, match="2 attempts"):
        app.run(TODAY)

    assert notifier.messages == []
    assert history.load() == []


def test_delivery_failure_does_not_mark_day_as_done(tmp_path: Path) -> None:
    class FailingNotifier(RecordingNotifier):
        def send(self, text: str) -> None:
            raise NotificationError("down")

    app, history, _ = _app(tmp_path, ScriptedSelector([make_ref()]), FailingNotifier())

    with pytest.raises(NotificationError):
        app.run(TODAY)

    assert history.load() == []


def test_main_returns_2_on_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)

    assert main(["--dry-run"]) == 2

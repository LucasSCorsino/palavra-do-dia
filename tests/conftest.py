"""Shared test doubles."""

import datetime as dt
from collections.abc import Sequence

import pytest

from palavra_do_dia.books import Book
from palavra_do_dia.errors import InvalidReferenceError, ProviderUnavailableError
from palavra_do_dia.models import HistoryEntry, PassageReference


def make_ref(
    book: str = "jo", chapter: int = 3, start: int = 16, end: int = 17
) -> PassageReference:
    return PassageReference(book=book, chapter=chapter, verse_start=start, verse_end=end)


def make_entry(ref: PassageReference, day: dt.date = dt.date(2026, 1, 1)) -> HistoryEntry:
    return HistoryEntry(date=day, reference=ref, version="NVI")


class FakeProvider:
    """Serves a fixed chapter, or raises ``error`` when set."""

    def __init__(
        self, version: str = "FAKE", verses: list[str] | None = None, error: Exception | None = None
    ) -> None:
        self._version = version
        self._verses = verses if verses is not None else [f"verse {n}" for n in range(1, 41)]
        self._error = error
        self.calls = 0

    @property
    def version(self) -> str:
        return self._version

    def get_chapter(self, book: Book, chapter: int) -> list[str]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._verses)


class ScriptedSelector:
    """Returns pre-defined references (or raises exceptions) in order."""

    def __init__(self, script: Sequence[PassageReference | Exception]) -> None:
        self._script = list(script)
        self.calls: list[tuple[Sequence[HistoryEntry], str, Sequence[str]]] = []

    def choose(
        self, recent: Sequence[HistoryEntry], focus_group: str, rejected: Sequence[str]
    ) -> PassageReference:
        self.calls.append((list(recent), focus_group, list(rejected)))
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)


@pytest.fixture
def unavailable() -> ProviderUnavailableError:
    return ProviderUnavailableError("down")


@pytest.fixture
def invalid() -> InvalidReferenceError:
    return InvalidReferenceError("nope")

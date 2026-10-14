"""Offline fallback provider reading a versioned JSON file."""

import json
import logging
from pathlib import Path

from palavra_do_dia.books import BOOKS, Book
from palavra_do_dia.errors import InvalidReferenceError, ProviderUnavailableError

logger = logging.getLogger(__name__)


class LocalBibleProvider:
    """Serves chapters from a JSON file shaped ``[{"chapters": [[verse, ...], ...]}, ...]``.

    Books must appear in canonical order (66 entries), matching ``palavra_do_dia.books``.
    """

    def __init__(self, path: Path, *, version: str) -> None:
        self._path = path
        self._version = version
        self._books: list[list[list[str]]] | None = None

    @property
    def version(self) -> str:
        return self._version

    def get_chapter(self, book: Book, chapter: int) -> list[str]:
        chapters = self._load()[book.index]
        if not 1 <= chapter <= len(chapters):
            raise InvalidReferenceError(f"{book.name} {chapter} does not exist")
        return list(chapters[chapter - 1])

    def _load(self) -> list[list[list[str]]]:
        if self._books is None:
            self._books = self._read_file()
        return self._books

    def _read_file(self) -> list[list[list[str]]]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            books = [entry["chapters"] for entry in raw]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ProviderUnavailableError(f"cannot read local Bible at {self._path}") from exc
        if len(books) != len(BOOKS):
            raise ProviderUnavailableError(
                f"local Bible has {len(books)} books, expected {len(BOOKS)}"
            )
        return books

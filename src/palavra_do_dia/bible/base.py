"""Provider contract."""

from typing import Protocol

from palavra_do_dia.books import Book


class BibleProvider(Protocol):
    """Fetches the verses of a whole chapter.

    Implementations raise:
      * ``InvalidReferenceError`` when the chapter does not exist.
      * ``ProviderUnavailableError`` when the source is down or returns garbage.
    """

    @property
    def version(self) -> str:
        """Translation label shown to the reader, e.g. ``NVI``."""
        ...

    def get_chapter(self, book: Book, chapter: int) -> list[str]:
        """Return the chapter's verse texts; index 0 is verse 1."""
        ...

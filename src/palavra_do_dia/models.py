"""Core domain models."""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from palavra_do_dia.books import Book, get_book

MAX_VERSES_PER_PASSAGE = 5


class PassageReference(BaseModel):
    """A validated pointer to 1-5 consecutive verses within one chapter."""

    model_config = ConfigDict(frozen=True)

    book: str
    chapter: int = Field(ge=1)
    verse_start: int = Field(ge=1)
    verse_end: int = Field(ge=1)

    @field_validator("book")
    @classmethod
    def _book_must_exist(cls, value: str) -> str:
        book = get_book(value)
        if book is None:
            raise ValueError(f"unknown book abbreviation: {value!r}")
        return book.abbrev

    @model_validator(mode="after")
    def _verse_range_must_be_valid(self) -> Self:
        if self.verse_end < self.verse_start:
            raise ValueError("verse_end must be >= verse_start")
        if self.verse_end - self.verse_start + 1 > MAX_VERSES_PER_PASSAGE:
            raise ValueError(f"a passage may have at most {MAX_VERSES_PER_PASSAGE} verses")
        return self

    @property
    def book_info(self) -> Book:
        book = get_book(self.book)
        if book is None:  # pragma: no cover - guarded by the validator
            raise ValueError(f"unknown book abbreviation: {self.book!r}")
        return book

    @property
    def label(self) -> str:
        """Human-readable reference, e.g. ``João 3:16-17``."""
        verses = (
            str(self.verse_start)
            if self.verse_start == self.verse_end
            else f"{self.verse_start}-{self.verse_end}"
        )
        return f"{self.book_info.name} {self.chapter}:{verses}"

    def overlaps(self, other: "PassageReference") -> bool:
        """True when both references share at least one verse."""
        return (
            self.book == other.book
            and self.chapter == other.chapter
            and self.verse_start <= other.verse_end
            and other.verse_start <= self.verse_end
        )


class Verse(BaseModel):
    number: int
    text: str


class Passage(BaseModel):
    """A reference together with its verbatim text from a specific translation."""

    reference: PassageReference
    verses: list[Verse]
    version: str


class HistoryEntry(BaseModel):
    """A passage that was already delivered."""

    date: dt.date
    reference: PassageReference
    version: str

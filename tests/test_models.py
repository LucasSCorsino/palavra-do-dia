import pytest
from pydantic import ValidationError

from palavra_do_dia.books import BOOKS, GROUPS, catalog_for_prompt, get_book
from palavra_do_dia.models import PassageReference


def test_catalog_has_66_books_in_canonical_order() -> None:
    assert len(BOOKS) == 66
    assert [book.index for book in BOOKS] == list(range(66))
    assert BOOKS[0].abbrev == "gn"
    assert BOOKS[42].abbrev == "jo"
    assert BOOKS[65].abbrev == "ap"


def test_every_book_belongs_to_a_known_group() -> None:
    assert {book.group for book in BOOKS} == set(GROUPS)


def test_get_book_is_case_insensitive_and_rejects_unknown() -> None:
    assert get_book(" JO ") is BOOKS[42]
    assert get_book("xx") is None


def test_catalog_for_prompt_lists_all_books() -> None:
    assert catalog_for_prompt().count("=") == 66


def test_reference_label_single_and_range() -> None:
    assert PassageReference(book="jo", chapter=3, verse_start=16, verse_end=16).label == "João 3:16"
    assert (
        PassageReference(book="sl", chapter=23, verse_start=1, verse_end=3).label == "Salmos 23:1-3"
    )


def test_reference_normalizes_book() -> None:
    assert PassageReference(book="  SL ", chapter=1, verse_start=1, verse_end=1).book == "sl"


@pytest.mark.parametrize(
    ("book", "chapter", "start", "end"),
    [
        ("zz", 1, 1, 1),  # unknown book
        ("jo", 0, 1, 1),  # chapter below 1
        ("jo", 1, 0, 1),  # verse below 1
        ("jo", 1, 5, 4),  # end before start
        ("jo", 1, 1, 6),  # more than 5 verses
    ],
)
def test_reference_rejects_invalid_input(book: str, chapter: int, start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        PassageReference(book=book, chapter=chapter, verse_start=start, verse_end=end)


def test_overlaps() -> None:
    base = PassageReference(book="jo", chapter=3, verse_start=16, verse_end=18)
    assert base.overlaps(PassageReference(book="jo", chapter=3, verse_start=18, verse_end=19))
    assert not base.overlaps(PassageReference(book="jo", chapter=3, verse_start=19, verse_end=20))
    assert not base.overlaps(PassageReference(book="jo", chapter=4, verse_start=16, verse_end=18))
    assert not base.overlaps(PassageReference(book="mt", chapter=3, verse_start=16, verse_end=18))

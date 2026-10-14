"""Canonical catalog of the 66 books, in the same order used by the local Bible data."""

from dataclasses import dataclass

_BOOKS: tuple[tuple[str, str], ...] = (
    ("gn", "Gênesis"), ("ex", "Êxodo"), ("lv", "Levítico"), ("nm", "Números"),
    ("dt", "Deuteronômio"), ("js", "Josué"), ("jz", "Juízes"), ("rt", "Rute"),
    ("1sm", "1º Samuel"), ("2sm", "2º Samuel"), ("1rs", "1º Reis"), ("2rs", "2º Reis"),
    ("1cr", "1º Crônicas"), ("2cr", "2º Crônicas"), ("ed", "Esdras"), ("ne", "Neemias"),
    ("et", "Ester"), ("job", "Jó"), ("sl", "Salmos"), ("pv", "Provérbios"),
    ("ec", "Eclesiastes"), ("ct", "Cânticos"), ("is", "Isaías"), ("jr", "Jeremias"),
    ("lm", "Lamentações de Jeremias"), ("ez", "Ezequiel"), ("dn", "Daniel"), ("os", "Oséias"),
    ("jl", "Joel"), ("am", "Amós"), ("ob", "Obadias"), ("jn", "Jonas"),
    ("mq", "Miquéias"), ("na", "Naum"), ("hc", "Habacuque"), ("sf", "Sofonias"),
    ("ag", "Ageu"), ("zc", "Zacarias"), ("ml", "Malaquias"), ("mt", "Mateus"),
    ("mc", "Marcos"), ("lc", "Lucas"), ("jo", "João"), ("at", "Atos"),
    ("rm", "Romanos"), ("1co", "1ª Coríntios"), ("2co", "2ª Coríntios"), ("gl", "Gálatas"),
    ("ef", "Efésios"), ("fp", "Filipenses"), ("cl", "Colossenses"), ("1ts", "1ª Tessalonicenses"),
    ("2ts", "2ª Tessalonicenses"), ("1tm", "1ª Timóteo"), ("2tm", "2ª Timóteo"), ("tt", "Tito"),
    ("fm", "Filemom"), ("hb", "Hebreus"), ("tg", "Tiago"), ("1pe", "1ª Pedro"),
    ("2pe", "2ª Pedro"), ("1jo", "1ª João"), ("2jo", "2ª João"), ("3jo", "3ª João"),
    ("jd", "Judas"), ("ap", "Apocalipse"),
)  # fmt: skip

# Half-open index ranges [start, end) into ``_BOOKS``.
_GROUP_RANGES: tuple[tuple[str, int, int], ...] = (
    ("Pentateuco", 0, 5),
    ("Livros históricos do Antigo Testamento", 5, 17),
    ("Livros poéticos e de sabedoria", 17, 22),
    ("Profetas maiores", 22, 27),
    ("Profetas menores", 27, 39),
    ("Evangelhos e Atos", 39, 44),
    ("Epístolas de Paulo", 44, 57),
    ("Epístolas gerais e Apocalipse", 57, 66),
)


@dataclass(frozen=True, slots=True)
class Book:
    """A canonical book. ``index`` is its zero-based position in the Bible."""

    abbrev: str
    name: str
    group: str
    index: int


def _build_catalog() -> tuple[Book, ...]:
    group_by_index = {
        index: group for group, start, end in _GROUP_RANGES for index in range(start, end)
    }
    return tuple(
        Book(abbrev=abbrev, name=name, group=group_by_index[index], index=index)
        for index, (abbrev, name) in enumerate(_BOOKS)
    )


BOOKS: tuple[Book, ...] = _build_catalog()
GROUPS: tuple[str, ...] = tuple(group for group, _, _ in _GROUP_RANGES)
_BY_ABBREV: dict[str, Book] = {book.abbrev: book for book in BOOKS}


def get_book(abbrev: str) -> Book | None:
    """Return the book for an abbreviation, or ``None`` if it is unknown."""
    return _BY_ABBREV.get(abbrev.strip().lower())


def catalog_for_prompt() -> str:
    """Compact ``abbrev=Name`` listing used to constrain the AI's answer."""
    return ", ".join(f"{book.abbrev}={book.name}" for book in BOOKS)

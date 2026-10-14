"""Orchestrates providers in priority order and slices the requested verses."""

import logging
from collections.abc import Sequence

from palavra_do_dia.bible.base import BibleProvider
from palavra_do_dia.errors import (
    AllProvidersFailedError,
    InvalidReferenceError,
    ProviderUnavailableError,
)
from palavra_do_dia.models import Passage, PassageReference, Verse

logger = logging.getLogger(__name__)


class BibleService:
    """Tries each provider in order; falls back only when a provider is unavailable."""

    def __init__(self, providers: Sequence[BibleProvider]) -> None:
        if not providers:
            raise ValueError("at least one Bible provider is required")
        self._providers = tuple(providers)

    def fetch(self, reference: PassageReference) -> Passage:
        failures: list[str] = []
        for provider in self._providers:
            try:
                chapter = provider.get_chapter(reference.book_info, reference.chapter)
            except ProviderUnavailableError as exc:
                logger.warning("Provider %s unavailable: %s", provider.version, exc)
                failures.append(f"{provider.version}: {exc}")
                continue
            return self._slice(reference, chapter, provider.version)
        raise AllProvidersFailedError("; ".join(failures))

    @staticmethod
    def _slice(reference: PassageReference, chapter: list[str], version: str) -> Passage:
        if reference.verse_end > len(chapter):
            raise InvalidReferenceError(
                f"{reference.label} is out of range: chapter has {len(chapter)} verses"
            )
        verses = [
            Verse(number=number, text=chapter[number - 1])
            for number in range(reference.verse_start, reference.verse_end + 1)
        ]
        return Passage(reference=reference, verses=verses, version=version)

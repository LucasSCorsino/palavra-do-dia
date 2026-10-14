"""Bible providers: dumb chapter fetchers behind a common interface."""

from palavra_do_dia.bible.base import BibleProvider
from palavra_do_dia.bible.local import LocalBibleProvider
from palavra_do_dia.bible.remote import AbibliaDigitalProvider
from palavra_do_dia.bible.service import BibleService

__all__ = ["AbibliaDigitalProvider", "BibleProvider", "BibleService", "LocalBibleProvider"]

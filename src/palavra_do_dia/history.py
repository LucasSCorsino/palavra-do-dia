"""Persistent record of delivered passages, used to avoid repetition and double sends."""

import datetime as dt
import json
import logging
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from palavra_do_dia.errors import DailyWordError
from palavra_do_dia.models import HistoryEntry, PassageReference

logger = logging.getLogger(__name__)

_ENTRIES = TypeAdapter(list[HistoryEntry])


class HistoryStore:
    """JSON-file-backed history. A missing file means an empty history."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[HistoryEntry]:
        if not self._path.exists():
            return []
        try:
            raw = self._path.read_text(encoding="utf-8-sig")
            return _ENTRIES.validate_json(raw)
        except (OSError, ValidationError) as exc:
            raise DailyWordError(f"history file {self._path} is unreadable or corrupt") from exc

    def recent(self, limit: int) -> list[HistoryEntry]:
        return self.load()[-limit:] if limit > 0 else []

    def has_entry_for(self, day: dt.date) -> bool:
        return any(entry.date == day for entry in self.load())

    def was_used(self, reference: PassageReference, window: int) -> bool:
        return any(entry.reference.overlaps(reference) for entry in self.recent(window))

    def append(self, entry: HistoryEntry) -> None:
        entries = [*self.load(), entry]
        payload = json.dumps(
            _ENTRIES.dump_python(entries, mode="json"), ensure_ascii=False, indent=2
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(payload + "\n", encoding="utf-8")
        temp_path.replace(self._path)

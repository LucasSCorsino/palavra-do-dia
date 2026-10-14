"""Use case: select, fetch, deliver and record today's passage."""

import datetime as dt
import logging
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from palavra_do_dia.bible import BibleService
from palavra_do_dia.books import GROUPS
from palavra_do_dia.errors import InvalidReferenceError, SelectionError
from palavra_do_dia.history import HistoryStore
from palavra_do_dia.models import HistoryEntry, Passage
from palavra_do_dia.notifier import Notifier, format_passage
from palavra_do_dia.selector import ReferenceSelector

logger = logging.getLogger(__name__)


def _random_group(groups: Sequence[str]) -> str:
    return random.choice(groups)


@dataclass
class DailyWord:
    selector: ReferenceSelector
    bible: BibleService
    history: HistoryStore
    notifier: Notifier
    history_window: int = 60
    max_attempts: int = 3
    choose_group: Callable[[Sequence[str]], str] = field(default=_random_group)

    def run(self, today: dt.date, *, force: bool = False, dry_run: bool = False) -> Passage | None:
        """Deliver today's passage. Returns ``None`` if already delivered today.

        With ``dry_run`` the message is only logged: nothing is sent or recorded.
        """
        if not (force or dry_run) and self.history.has_entry_for(today):
            logger.info("Already delivered for %s; nothing to do.", today)
            return None

        passage = self._pick_passage()
        message = format_passage(passage)

        if dry_run:
            logger.info("Dry run, message not sent:\n%s", message)
            return passage

        # Send before recording so a delivery failure does not mark the day as done.
        self.notifier.send(message)
        self.history.append(
            HistoryEntry(date=today, reference=passage.reference, version=passage.version)
        )
        logger.info("Delivered %s (%s).", passage.reference.label, passage.version)
        return passage

    def _pick_passage(self) -> Passage:
        recent = self.history.recent(self.history_window)
        focus_group = self.choose_group(GROUPS)
        rejected: list[str] = []

        for attempt in range(1, self.max_attempts + 1):
            try:
                reference = self.selector.choose(recent, focus_group, rejected)
                if any(reference.overlaps(entry.reference) for entry in recent):
                    raise InvalidReferenceError(f"{reference.label} was used recently")
                return self.bible.fetch(reference)
            except InvalidReferenceError as exc:
                logger.warning("Attempt %d/%d rejected: %s", attempt, self.max_attempts, exc)
                rejected.append(str(exc))

        raise SelectionError(
            f"no valid passage after {self.max_attempts} attempts: {'; '.join(rejected)}"
        )

"""Bounded, user-requested management of existing local memory records."""
from dataclasses import dataclass
from datetime import datetime, timezone

from companion.domain.errors import NotFoundError, ValidationError
from companion.domain.models import Memory, MemoryKind, MemoryQuery
from companion.ports.clock import Clock
from companion.ports.repositories import MemoryRepository

PAGE_SIZE = 50


@dataclass(frozen=True)
class MemoryPage:
    records: tuple[Memory, ...]
    observed_at: datetime
    offset: int
    has_next: bool


class MemoryManagementService:
    def __init__(self, repository: MemoryRepository, clock: Clock):
        self.repository, self.clock = repository, clock

    def list_page(self, text: str = '', kind: MemoryKind | None = None,
                  include_expired: bool = True, offset: int = 0) -> MemoryPage:
        if type(offset) is not int or offset < 0 or not isinstance(text, str):
            raise ValidationError('Invalid memory management query.')
        query = MemoryQuery(text=text.strip(), kind=kind, include_expired=include_expired)
        now = self.clock.now_utc()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError('Memory management requires an aware clock.')
        now = now.astimezone(timezone.utc)
        records = self.repository.search(query, limit=PAGE_SIZE + 1, as_of_utc=now, offset=offset)
        return MemoryPage(tuple(records[:PAGE_SIZE]), now, offset, len(records) > PAGE_SIZE)

    def delete(self, memory_id: str) -> bool:
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValidationError('A selected memory is required.')
        try:
            self.repository.delete(memory_id)
            return True
        except NotFoundError:
            return False

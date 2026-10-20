from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from companion.application.memory_management import MemoryManagementService, PAGE_SIZE
from companion.domain.errors import NotFoundError, ValidationError
from companion.domain.models import Memory, MemoryKind

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


class Repository:
    def __init__(self):
        self.items = [Memory(str(i), MemoryKind.PROFILE, f'public item {i}', created_at=NOW) for i in range(51)]
        self.calls = []

    def search(self, query, limit, **kwargs):
        self.calls.append((query, limit, kwargs))
        offset = kwargs['offset']
        return self.items[offset:offset + limit]

    def delete(self, memory_id):
        self.calls.append(('delete', memory_id))
        if not any(item.id == memory_id for item in self.items):
            raise NotFoundError()
        self.items = [item for item in self.items if item.id != memory_id]


def test_management_uses_injected_clock_bounded_lookahead_and_explicit_query():
    repository = Repository()
    ticks = []
    service = MemoryManagementService(repository, SimpleNamespace(now_utc=lambda: (ticks.append(1), NOW)[1]))
    assert not repository.calls and not ticks
    page = service.list_page(' public ', MemoryKind.PROFILE)
    assert len(page.records) == PAGE_SIZE == 50 and page.has_next and page.offset == 0
    assert page.observed_at == NOW and ticks == [1]
    query, limit, kwargs = repository.calls[-1]
    assert query.text == 'public' and query.kind == MemoryKind.PROFILE and query.include_expired
    assert limit == 51 and kwargs == {'as_of_utc': NOW, 'offset': 0}
    page = service.list_page(include_expired=False, offset=50)
    assert len(page.records) == 1 and not page.has_next and page.offset == 50
    assert not repository.calls[-1][0].include_expired


@pytest.mark.parametrize('kwargs', [{'offset': -1}, {'offset': True}, {'text': None}, {'include_expired': 'yes'}, {'kind': 'invalid'}])
def test_invalid_management_query_does_not_access_repository(kwargs):
    repository = Repository()
    service = MemoryManagementService(repository, SimpleNamespace(now_utc=lambda: NOW))
    with pytest.raises(ValidationError):
        service.list_page(**kwargs)
    assert repository.calls == []


def test_naive_clock_is_rejected_without_storage_access():
    repository = Repository()
    service = MemoryManagementService(repository, SimpleNamespace(now_utc=lambda: NOW.replace(tzinfo=None)))
    with pytest.raises(ValidationError):
        service.list_page()
    assert repository.calls == []


def test_targeted_delete_is_idempotent_without_changing_other_records():
    repository = Repository()
    service = MemoryManagementService(repository, SimpleNamespace(now_utc=lambda: NOW))
    assert service.delete('3') is True
    assert service.delete('3') is False
    assert len(repository.items) == 50 and repository.items[0].id == '0'
    with pytest.raises(ValidationError):
        service.delete(' ')

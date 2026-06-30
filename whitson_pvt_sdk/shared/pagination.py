from collections.abc import Callable, Iterator
from typing import Any, TypeVar

_T = TypeVar("_T")


class Paginator:
    @staticmethod
    def iterate(
        page_fn: Callable[..., Any],
        items_field: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> Iterator[_T]:
        while True:
            page = page_fn(cursor=cursor, limit=limit, **kwargs)
            yield from getattr(page, items_field)
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    @staticmethod
    def list_all(
        page_fn: Callable[..., Any],
        items_field: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[_T]:
        return list(Paginator.iterate(page_fn, items_field, cursor=cursor, limit=limit, **kwargs))

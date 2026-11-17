from collections.abc import Callable, Sequence
from typing import Annotated, Protocol

import typer
from pydantic import BaseModel, ConfigDict, SerializeAsAny

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.cli._export import export_black_oil_table, export_samples
from whitson_pvt_sdk.cli._output import JsonOption, emit, emit_data, note, reporting
from whitson_pvt_sdk.shared.pagination import Paginator
from whitson_pvt_sdk.v2.models import PaginationMeta


class _Page(Protocol):
    @property
    def pagination(self) -> PaginationMeta: ...


class Parent(BaseModel):
    model_config = ConfigDict(frozen=True)

    flag: str
    help: str


class TopLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    items_field: str
    page: Callable[[WhitsonPVTClient, str | None, int | None], _Page]


class Nested(BaseModel):
    model_config = ConfigDict(frozen=True)

    parent: Parent
    items_field: str
    page: Callable[[WhitsonPVTClient, int, str | None, int | None], _Page]


class Unpaged(BaseModel):
    model_config = ConfigDict(frozen=True)

    parent: Parent
    items: Callable[[WhitsonPVTClient, int], Sequence[BaseModel]]


class Resource(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    plural: str
    noun: str
    aliases: tuple[str, ...] = ()
    listing: TopLevel | Nested | Unpaged
    get: Callable[[WhitsonPVTClient, int], BaseModel]
    export: Callable[..., None] | None = None


RESOURCES = (
    Resource(
        name="regions",
        plural="regions",
        noun="region",
        listing=TopLevel(
            items_field="regions",
            page=lambda client, cursor, limit: client.regions.list(cursor=cursor, limit=limit),
        ),
        get=lambda client, id: client.regions.get(id),
    ),
    Resource(
        name="wells",
        plural="wells",
        noun="well",
        listing=Nested(
            parent=Parent(flag="--region", help="Region whose wells to list."),
            items_field="wells",
            page=lambda client, parent, cursor, limit: client.wells.list(
                parent, cursor=cursor, limit=limit
            ),
        ),
        get=lambda client, id: client.wells.get(id),
    ),
    Resource(
        name="samples",
        plural="samples",
        noun="sample",
        listing=Unpaged(
            parent=Parent(flag="--well", help="Well whose samples to list."),
            items=lambda client, parent: client.samples.list(parent).samples,
        ),
        get=lambda client, id: client.samples.get(id),
        export=export_samples,
    ),
    Resource(
        name="projects",
        plural="projects",
        noun="project",
        listing=Nested(
            parent=Parent(flag="--region", help="Region whose projects to list."),
            items_field="projects",
            page=lambda client, parent, cursor, limit: client.projects.list(
                parent, cursor=cursor, limit=limit
            ),
        ),
        get=lambda client, id: client.projects.get(id),
    ),
    Resource(
        name="fluid-models",
        plural="fluid models",
        noun="fluid model",
        listing=Nested(
            parent=Parent(flag="--project", help="Project whose fluid models to list."),
            items_field="fluid_models",
            page=lambda client, parent, cursor, limit: client.fluid_models.list(
                parent, cursor=cursor, limit=limit
            ),
        ),
        get=lambda client, id: client.fluid_models.get(id),
    ),
    Resource(
        name="bot",
        aliases=("black-oil-tables",),
        plural="black-oil tables (BOT)",
        noun="black-oil table",
        listing=Nested(
            parent=Parent(flag="--fluid-model", help="Fluid model whose black-oil tables to list."),
            items_field="black_oil_tables",
            page=lambda client, parent, cursor, limit: client.black_oil_tables.list(
                parent, cursor=cursor, limit=limit
            ),
        ),
        get=lambda client, id: client.black_oil_tables.get(id),
        export=export_black_oil_table,
    ),
)


class Listing(BaseModel):
    items: list[SerializeAsAny[BaseModel]]
    next_cursor: str | None


LimitOption = Annotated[
    int | None,
    typer.Option("--limit", min=1, max=250, help="Page size; the API default (20) otherwise."),
]
CursorOption = Annotated[
    str | None, typer.Option("--cursor", help="Start at this next_cursor from an earlier page.")
]
AllOption = Annotated[bool, typer.Option("--all", help="Follow the pages to the end.")]


def resource_app(resource: Resource) -> typer.Typer:
    verbs = "List and show" if resource.export is None else "List, show and export"
    aliases = f" Alias: {', '.join(resource.aliases)}." if resource.aliases else ""
    group = typer.Typer(help=f"{verbs} {resource.plural}.{aliases}", no_args_is_help=True)
    group.command("list", help=_list_help(resource))(_list_command(resource))
    group.command("get", help=f"Print one {resource.noun} as JSON.")(_get_command(resource))
    if resource.export is not None:
        group.command("export")(resource.export)
    return group


def _list_help(resource: Resource) -> str:
    match resource.listing:
        case TopLevel():
            return f"List {resource.plural}, one page unless --all."
        case Nested(parent=parent):
            return f"List {resource.plural} under {parent.flag}, one page unless --all."
        case Unpaged(parent=parent):
            return f"List every {resource.noun} under {parent.flag}."


def _list_command(resource: Resource) -> Callable[..., None]:
    match resource.listing:
        case TopLevel() as listing:

            def top_level(
                limit: LimitOption = None,
                cursor: CursorOption = None,
                every: AllOption = False,
                json_output: JsonOption = False,
            ) -> None:
                with reporting(json_output=json_output), WhitsonPVTClient() as client:
                    _emit_listing(
                        _paged(
                            lambda cursor, limit: listing.page(client, cursor, limit),
                            listing.items_field,
                            cursor=cursor,
                            limit=limit,
                            every=every,
                        ),
                        json_output,
                    )

            return top_level
        case Nested(parent=parent) as listing:

            def nested(
                parent_id: Annotated[int, typer.Option(parent.flag, help=parent.help)],
                limit: LimitOption = None,
                cursor: CursorOption = None,
                every: AllOption = False,
                json_output: JsonOption = False,
            ) -> None:
                with reporting(json_output=json_output), WhitsonPVTClient() as client:
                    _emit_listing(
                        _paged(
                            lambda cursor, limit: listing.page(client, parent_id, cursor, limit),
                            listing.items_field,
                            cursor=cursor,
                            limit=limit,
                            every=every,
                        ),
                        json_output,
                    )

            return nested
        case Unpaged(parent=parent) as listing:

            def unpaged(
                parent_id: Annotated[int, typer.Option(parent.flag, help=parent.help)],
                json_output: JsonOption = False,
            ) -> None:
                with reporting(json_output=json_output), WhitsonPVTClient() as client:
                    items = listing.items(client, parent_id)
                    _emit_listing(Listing(items=list(items), next_cursor=None), json_output)

            return unpaged


def _get_command(resource: Resource) -> Callable[..., None]:
    def get(
        id: Annotated[int, typer.Argument(metavar="ID", help=f"The {resource.noun}'s id.")],
        json_output: JsonOption = False,
    ) -> None:
        with reporting(json_output=json_output), WhitsonPVTClient() as client:
            emit_data(resource.get(client, id))

    return get


def _paged(
    page: Callable[[str | None, int | None], _Page],
    items_field: str,
    *,
    cursor: str | None,
    limit: int | None,
    every: bool,
) -> Listing:
    if every:
        items = Paginator.iterate(page, items_field, cursor=cursor, limit=limit)
        return Listing(items=list(items), next_cursor=None)
    first = page(cursor, limit)
    return Listing(items=getattr(first, items_field), next_cursor=first.pagination.next_cursor)


def _emit_listing(listing: Listing, json_output: bool) -> None:
    rows = [item.model_dump(include={"id", "name"}) for item in listing.items]
    emit(
        listing,
        "\n".join(f"{row['id']}\t{row.get('name') or ''}" for row in rows),
        json_output=json_output,
    )
    if listing.next_cursor is not None and not json_output:
        note(f"More results: pass --cursor {listing.next_cursor}, or --all.")

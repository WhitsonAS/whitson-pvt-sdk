import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.cli._output import emit, note, reporting
from whitson_pvt_sdk.errors import ConfigurationError
from whitson_pvt_sdk.http import API_PREFIX, route_segments
from whitson_pvt_sdk.shared.models import ApiResponse, HTTPMethod
from whitson_pvt_sdk.shared.pagination import Paginator
from whitson_pvt_sdk.v2.models import PaginationMeta

OPENAPI_PATH = "/docs/openapi.json"
RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "retry-after",
)

Body = dict[str, JsonValue] | list[dict[str, JsonValue]]
_method: TypeAdapter[HTTPMethod] = TypeAdapter(HTTPMethod)
_body: TypeAdapter[Body] = TypeAdapter(Body)


class Call(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: HTTPMethod
    path: str
    params: dict[str, str]
    body: Body | None
    paginate: bool
    include: bool
    out: Path | None


class ListRoutes(BaseModel):
    model_config = ConfigDict(frozen=True)


class Describe(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: HTTPMethod | None
    path: str


class Parameter(BaseModel):
    name: str
    location: str
    required: bool
    type: str | None


class Route(BaseModel):
    method: HTTPMethod
    path: str
    summary: str | None


class RouteDetail(Route):
    scopes: list[str]
    parameters: list[Parameter]
    request_schema: str | None
    response_schemas: dict[str, str | None]


class Routes(BaseModel):
    routes: tuple[Route, ...]


class RouteDetails(BaseModel):
    routes: list[RouteDetail]


class _SpecParameter(BaseModel):
    name: str
    location: str = Field(alias="in")
    required: bool = False
    schema_: dict[str, JsonValue] = Field(default_factory=dict, alias="schema")


class _SpecMedia(BaseModel):
    schema_: dict[str, JsonValue] = Field(default_factory=dict, alias="schema")


class _SpecBody(BaseModel):
    content: dict[str, _SpecMedia] = Field(default_factory=dict)


class _SpecOperation(BaseModel):
    summary: str | None = None
    parameters: list[_SpecParameter] = Field(default_factory=list)
    request_body: _SpecBody | None = Field(default=None, alias="requestBody")
    responses: dict[str, _SpecBody] = Field(default_factory=dict)
    security: list[dict[str, list[str]]] = Field(default_factory=list)


class _Spec(BaseModel):
    paths: dict[str, dict[str, JsonValue]]


class _CursorPage(BaseModel):
    model_config = ConfigDict(extra="allow")

    pagination: PaginationMeta

    def items_field(self) -> str | None:
        lists = [key for key, value in (self.model_extra or {}).items() if isinstance(value, list)]
        return lists[0] if len(lists) == 1 else None


def api_command(
    target: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[METHOD] PATH", help="Such as /regions or POST /calculations/flash."
        ),
    ] = None,
    query: Annotated[
        list[str] | None,
        typer.Option("--query", "-q", metavar="KEY=VALUE", help="Query parameter; repeatable."),
    ] = None,
    data: Annotated[
        str | None,
        typer.Option(
            "--data", "-d", help="JSON body: inline, @FILE, or - for stdin. Implies POST."
        ),
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", dir_okay=False, help="Write the body here.")
    ] = None,
    paginate: Annotated[
        bool,
        typer.Option("--paginate", help="Follow pagination.next_cursor and print one document."),
    ] = False,
    include: Annotated[
        bool,
        typer.Option("--include", "-i", help="Print the status and rate-limit headers to stderr."),
    ] = False,
    list_routes: Annotated[
        bool, typer.Option("--list", help="List the deployment's external v2 routes.")
    ] = False,
    describe: Annotated[
        bool,
        typer.Option("--describe", help="Show the parameters and schemas of [METHOD] PATH."),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="With --list or --describe: one JSON document.")
    ] = False,
) -> None:
    """Call any external v2 route, PATH relative to /external/v2 (like gh api).

    METHOD defaults to GET, or POST with --data. The response body goes to stdout or --out.
    """
    with reporting(json_output=json_output):
        mode = _mode(target or [], query or [], data, out, paginate, include, list_routes, describe)
        with WhitsonPVTClient() as client:
            match mode:
                case Call():
                    _call(client, mode)
                case ListRoutes():
                    routes = _routes(client)
                    emit(
                        Routes(routes=tuple(routes)),
                        "\n".join(
                            f"{route.method:<7}{route.path:<55}{route.summary or ''}".rstrip()
                            for route in routes
                        ),
                        json_output=json_output,
                    )
                case Describe(method=method, path=path):
                    matches = [
                        route
                        for route in _routes(client)
                        if (method is None or route.method == method) and _matches(route.path, path)
                    ]
                    if not matches:
                        wanted = path if method is None else f"{method} {path}"
                        raise ConfigurationError(
                            f"No route matches {wanted}. Run `wpvt api --list`."
                        )
                    emit(
                        RouteDetails(routes=matches),
                        "\n\n".join(_describe(route) for route in matches),
                        json_output=json_output,
                    )


def _mode(
    target: list[str],
    query: list[str],
    data: str | None,
    out: Path | None,
    paginate: bool,
    include: bool,
    list_routes: bool,
    describe: bool,
) -> Call | ListRoutes | Describe:
    request_options = bool(query or data is not None or out or paginate or include)
    match (list_routes, describe, target):
        case (True, True, _):
            raise ConfigurationError("Pass either --list or --describe.")
        case (True, False, []) if not request_options:
            return ListRoutes()
        case (True, False, _):
            raise ConfigurationError("--list takes no PATH and no request options.")
        case (False, True, [_, *_]) if not request_options:
            method, path = _method_and_path(target)
            return Describe(method=method, path=path)
        case (False, True, _):
            raise ConfigurationError("--describe takes [METHOD] PATH and no request options.")
        case (False, False, [_, *_]):
            body = None if data is None else _parse_body(data)
            method, path = _method_and_path(target)
            method = method or ("GET" if body is None else "POST")
            if paginate and method != "GET":
                raise ConfigurationError("--paginate applies only to GET.")
            return Call(
                method=method,
                path=path,
                params=_parse_query(query),
                body=body,
                paginate=paginate,
                include=include,
                out=out,
            )
        case _:
            raise ConfigurationError("Give a PATH such as /regions, or pass --list.")


def _method_and_path(target: list[str]) -> tuple[HTTPMethod | None, str]:
    match target:
        case [path]:
            return None, path
        case [method, path]:
            try:
                return _method.validate_python(method.upper()), path
            except PydanticValidationError:
                raise ConfigurationError(
                    f"{method!r} is not one of GET, POST, PUT, PATCH, DELETE."
                ) from None
        case _:
            raise ConfigurationError("Give at most METHOD and PATH.")


def _parse_query(pairs: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            raise ConfigurationError(f"--query takes KEY=VALUE, not {pair!r}.")
        if key in params:
            raise ConfigurationError(f"--query {key} is given twice.")
        params[key] = value
    return params


def _parse_body(data: str) -> Body:
    if data == "-":
        text, source = sys.stdin.read(), "stdin"
    elif data.startswith("@"):
        try:
            text, source = Path(data[1:]).read_text(), data[1:]
        except OSError as exc:
            raise ConfigurationError(f"Cannot read {data[1:]}: {exc.strerror}.") from None
    else:
        text, source = data, "--data"
    try:
        return _body.validate_json(text)
    except PydanticValidationError:
        raise ConfigurationError(
            f"The body from {source} is not a JSON object or a list of objects."
        ) from None


def _call(client: WhitsonPVTClient, call: Call) -> None:
    def send(params: dict[str, str]) -> ApiResponse:
        response = client.request(call.method, call.path, params=params or None, body=call.body)
        if call.include:
            _print_status(response)
        return response

    first = send(call.params)
    if not call.paginate:
        content = first.content
    else:
        content = (_paginated(first, call, send) + "\n").encode()
    if call.out is None:
        typer.echo(content, nl=False)
    else:
        call.out.write_bytes(content)
        note(f"Wrote {call.out}")


def _paginated(
    first: ApiResponse, call: Call, send: Callable[[dict[str, str]], ApiResponse]
) -> str:
    try:
        page = _CursorPage.model_validate_json(first.content)
    except PydanticValidationError:
        page = None
    field = None if page is None else page.items_field()
    if page is None or field is None:
        raise ConfigurationError(
            f"{call.path} does not answer with cursor pagination (pagination.next_cursor next "
            "to one list); run it without --paginate."
        )

    def next_page(cursor: str | None, limit: int | None) -> _CursorPage:
        params = call.params if cursor is None else {**call.params, "cursor": cursor}
        return _CursorPage.model_validate_json(send(params).content)

    cursor = page.pagination.next_cursor
    rest = [] if cursor is None else list(Paginator.iterate(next_page, field, cursor=cursor))
    return json.dumps(
        {
            **(page.model_extra or {}),
            field: [*getattr(page, field), *rest],
            "pagination": {"next_cursor": None, "prev_cursor": None},
        },
        indent=2,
    )


def _print_status(response: ApiResponse) -> None:
    note(f"HTTP {response.status_code}")
    for name in RATE_LIMIT_HEADERS:
        if name in response.headers:
            note(f"{name}: {response.headers[name]}")


def _routes(client: WhitsonPVTClient) -> list[RouteDetail]:
    try:
        spec = _Spec.model_validate_json(client.request("GET", OPENAPI_PATH).content)
    except PydanticValidationError:
        raise ConfigurationError(
            f"{API_PREFIX}{OPENAPI_PATH} is not an OpenAPI document with paths."
        ) from None
    routes: list[RouteDetail] = []
    for path, item in spec.paths.items():
        for method, operation in item.items():
            try:
                parsed_method = _method.validate_python(method.upper())
                parsed = _SpecOperation.model_validate(operation)
            except PydanticValidationError:
                continue
            routes.append(
                RouteDetail(
                    method=parsed_method,
                    path="/" + path.removeprefix(API_PREFIX).lstrip("/"),
                    summary=parsed.summary,
                    scopes=list(
                        dict.fromkeys(
                            scope
                            for requirement in parsed.security
                            for scopes in requirement.values()
                            for scope in scopes
                        )
                    ),
                    parameters=[
                        Parameter(
                            name=parameter.name,
                            location=parameter.location,
                            required=parameter.required,
                            type=_schema_name(parameter.schema_),
                        )
                        for parameter in parsed.parameters
                    ],
                    request_schema=_body_schema(parsed.request_body),
                    response_schemas={
                        status: _body_schema(body) for status, body in parsed.responses.items()
                    },
                )
            )
    return sorted(routes, key=lambda route: (route.path, route.method))


def _body_schema(body: _SpecBody | None) -> str | None:
    if body is None or not body.content:
        return None
    media = body.content.get("application/json") or next(iter(body.content.values()))
    return _schema_name(media.schema_)


def _schema_name(schema: dict[str, JsonValue]) -> str | None:
    match schema:
        case {"$ref": str(ref)}:
            return ref.rsplit("/", 1)[-1]
        case {"type": "array", "items": {"$ref": str(ref)}}:
            return f"list[{ref.rsplit('/', 1)[-1]}]"
        case {"type": str(kind)}:
            return kind
        case {"title": str(title)}:
            return title
        case _:
            return None


def _matches(template: str, path: str) -> bool:
    wanted = route_segments(path)
    pattern = template.removeprefix("/").split("/")
    return len(pattern) == len(wanted) and all(
        given == expected or (expected.startswith("{") and expected.endswith("}"))
        for expected, given in zip(pattern, wanted, strict=True)
    )


def _describe(route: RouteDetail) -> str:
    lines = [f"{route.method} {route.path}"]
    if route.summary:
        lines.append(f"  {route.summary}")
    if route.scopes:
        lines.append(f"  scopes: {', '.join(route.scopes)}")
    for parameter in route.parameters:
        required = ", required" if parameter.required else ""
        lines.append(
            f"  {parameter.location} {parameter.name} ({parameter.type or 'any'}{required})"
        )
    lines.append(f"  request: {route.request_schema or '-'}")
    for status, schema in route.response_schemas.items():
        lines.append(f"  response {status}: {schema or '-'}")
    return "\n".join(lines)

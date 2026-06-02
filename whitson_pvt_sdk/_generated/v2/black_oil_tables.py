from ...http import HTTPTransport
from ...models.manual import PaginationParams
from ...v2.models import (
    GetBlackOilTableModel,
    PaginatedBlackOilTablesModel,
)


def list_black_oil_tables(
    transport: HTTPTransport,
    fluid_model_id: int,
    cursor: str | None = None,
    limit: int | None = None,
) -> PaginatedBlackOilTablesModel:
    params = PaginationParams(cursor=cursor, limit=limit).model_dump(exclude_none=True)
    body = transport.get(
        f"/fluid-models/{fluid_model_id}/black-oil-tables",
        params=params,
    )
    return PaginatedBlackOilTablesModel.model_validate(body)


def get_black_oil_table(transport: HTTPTransport, black_oil_table_id: int) -> GetBlackOilTableModel:
    body = transport.get(f"/black-oil-tables/{black_oil_table_id}")
    return GetBlackOilTableModel.model_validate(body)

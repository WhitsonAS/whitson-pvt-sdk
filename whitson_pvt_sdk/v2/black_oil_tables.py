from ..http import HTTPTransport
from ..models.v2._generated import (
    GetBlackOilTableModel,
    PaginatedBlackOilTablesModel,
)


def list_black_oil_tables(
    transport: HTTPTransport, fluid_model_id: int
) -> PaginatedBlackOilTablesModel:
    body = transport.get(f"/fluid-models/{fluid_model_id}/black-oil-tables")
    return PaginatedBlackOilTablesModel.model_validate(body)


def get_black_oil_table(
    transport: HTTPTransport, black_oil_table_id: int
) -> GetBlackOilTableModel:
    body = transport.get(f"/black-oil-tables/{black_oil_table_id}")
    return GetBlackOilTableModel.model_validate(body)

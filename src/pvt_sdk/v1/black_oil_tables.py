from .._models import (
    ExternalBlackOilTablesListModel,
    ExternalGetBlackOilTableModel,
)
from ..http import HTTPTransport


def list_black_oil_tables(
    transport: HTTPTransport, fluid_model_id: int
) -> ExternalBlackOilTablesListModel:
    body = transport.get(f"/fluid-models/{fluid_model_id}/black-oil-tables")
    return ExternalBlackOilTablesListModel.model_validate(body)


def get_black_oil_table(
    transport: HTTPTransport, black_oil_table_id: int
) -> ExternalGetBlackOilTableModel:
    body = transport.get(f"/black-oil-tables/{black_oil_table_id}")
    return ExternalGetBlackOilTableModel.model_validate(body)

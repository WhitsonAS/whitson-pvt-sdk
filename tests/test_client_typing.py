from typing import TYPE_CHECKING

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.models.manual import ClientCredentials
from whitson_pvt_sdk.models.v1._generated import RegionsListModel
from whitson_pvt_sdk.models.v2._generated import PaginatedRegionsModel
from whitson_pvt_sdk.v1 import WhitsonPVTClientV1
from whitson_pvt_sdk.v1.resources import Regions as V1Regions
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2
from whitson_pvt_sdk.v2.resources import Regions as V2Regions

if TYPE_CHECKING:
    credentials = ClientCredentials(client_id="", client_secret="")

    default_client = WhitsonPVTClient(credentials=credentials, base_url="")
    default_client_type: WhitsonPVTClientV2 = default_client
    default_regions: V2Regions = default_client.regions
    default_region_list: PaginatedRegionsModel = default_client.regions.list()

    legacy_client = WhitsonPVTClient(credentials=credentials, base_url="", version="v1")
    legacy_client_type: WhitsonPVTClientV1 = legacy_client
    legacy_regions: V1Regions = legacy_client.regions
    legacy_region_list: RegionsListModel = legacy_client.regions.list()

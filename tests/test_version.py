from importlib import metadata

import whitson_pvt_sdk


def test_package_version_comes_from_metadata():
    assert whitson_pvt_sdk.__version__ == metadata.version("whitson-pvt-sdk")

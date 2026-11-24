import json

import pytest
from typer.testing import CliRunner

from tests.conftest import NAMELESS_WELL
from tests.v2.test_calculations import make_fluid_model_json
from whitson_pvt_sdk.cli._app import app

BASE = "https://dev.pvt.whitson.com"
API = f"{BASE}/external/v2"
TOKEN = "env-token"
TABLE_UNITS = {"reservoir_pressure_unit": "bara", "reservoir_temperature_unit": "C"}

runner = CliRunner()


@pytest.fixture(autouse=True)
def _api_token(monkeypatch):
    monkeypatch.setenv("WHITSON_PVT_URL", BASE)
    monkeypatch.setenv("WHITSON_PVT_TOKEN", TOKEN)


def _page(field, items, next_cursor=None):
    return {field: items, "pagination": {"next_cursor": next_cursor, "prev_cursor": None}}


@pytest.mark.parametrize(
    ("args", "route", "field", "item"),
    [
        (["regions"], "/regions", "regions", {}),
        (["wells", "--region", "3"], "/regions/3/wells", "wells", NAMELESS_WELL),
        (["projects", "--region", "3"], "/regions/3/projects", "projects", {}),
        (["fluid-models", "--project", "4"], "/projects/4/fluid-models", "fluid_models", {}),
        (
            ["bot", "--fluid-model", "5"],
            "/fluid-models/5/black-oil-tables",
            "black_oil_tables",
            TABLE_UNITS,
        ),
        (
            ["black-oil-tables", "--fluid-model", "5"],
            "/fluid-models/5/black-oil-tables",
            "black_oil_tables",
            TABLE_UNITS,
        ),
    ],
    ids=["regions", "wells", "projects", "fluid-models", "bot", "bot-alias"],
)
def test_list_all_follows_the_pages_and_prints_one_document(httpx2_mock, args, route, field, item):
    httpx2_mock.add_response(
        url=f"{API}{route}?limit=1", json=_page(field, [{**item, "id": 1}], "c2")
    )
    httpx2_mock.add_response(
        url=f"{API}{route}?cursor=c2&limit=1", json=_page(field, [{**item, "id": 2}])
    )

    result = runner.invoke(app, [args[0], "list", *args[1:], "--limit", "1", "--all", "--json"])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert [entry["id"] for entry in document["items"]] == [1, 2]
    assert document["next_cursor"] is None
    assert len(httpx2_mock.get_requests()) == 2


def test_list_without_all_prints_one_page_and_its_cursor(httpx2_mock):
    httpx2_mock.add_response(
        url=f"{API}/regions?cursor=c1",
        json=_page("regions", [{"id": 7, "name": "North"}], "c2"),
        is_reusable=True,
    )

    result = runner.invoke(app, ["regions", "list", "--cursor", "c1", "--json"])
    text = runner.invoke(app, ["regions", "list", "--cursor", "c1"])

    assert json.loads(result.stdout) == {
        "items": [
            {
                "id": 7,
                "name": "North",
                "note": None,
                "public": None,
                "region_type": None,
                "reservoir_type": None,
            }
        ],
        "next_cursor": "c2",
    }
    assert text.stdout == "7\tNorth\n"
    assert "--cursor c2" in text.stderr


def test_samples_list_reads_the_well(httpx2_mock):
    httpx2_mock.add_response(
        url=f"{API}/wells/6", json={**NAMELESS_WELL, "id": 6, "samples": [{"id": 8}]}
    )

    result = runner.invoke(app, ["samples", "list", "--well", "6", "--json"])

    assert result.exit_code == 0, result.stderr
    assert [item["id"] for item in json.loads(result.stdout)["items"]] == [8]


@pytest.mark.parametrize(
    ("resource", "route", "body"),
    [
        ("regions", "/regions/9", {"id": 9}),
        ("wells", "/wells/9", {**NAMELESS_WELL, "id": 9, "samples": []}),
        ("samples", "/samples/9", {"id": 9}),
        ("projects", "/projects/9", {"id": 9, "fluid_models": [], "samples": []}),
        ("fluid-models", "/fluid-models/9", {**make_fluid_model_json([]), "id": 9}),
    ],
    ids=["regions", "wells", "samples", "projects", "fluid-models"],
)
def test_get_prints_the_resource(httpx2_mock, resource, route, body):
    httpx2_mock.add_response(url=f"{API}{route}", json=body)

    result = runner.invoke(app, [resource, "get", "9"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["id"] == 9
    assert httpx2_mock.get_requests()[0].headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize(
    ("status", "exit_code", "kind"),
    [
        (400, 5, "refused"),
        (404, 5, "refused"),
        (409, 5, "refused"),
        (422, 5, "refused"),
        (401, 3, "authentication"),
        (408, 4, "server"),
        (429, 4, "server"),
        (500, 4, "server"),
    ],
)
@pytest.mark.usefixtures("no_retry_sleep")
def test_get_with_json_reports_a_failure_as_json(httpx2_mock, status, exit_code, kind):
    httpx2_mock.add_response(
        url=f"{API}/wells/9",
        status_code=status,
        json={"message": "Well 9 failed"},
        headers={"x-request-id": "req-9"},
        is_reusable=True,
    )

    result = runner.invoke(app, ["wells", "get", "9", "--json"])

    assert result.exit_code == exit_code
    assert result.stdout == ""
    assert json.loads(result.stderr) == {
        "error": kind,
        "message": "Well 9 failed",
        "status": status,
        "request_id": "req-9",
    }


COMPOSITION = {
    "components": [{"name": "C1", "input_name": "=cmd|' /C calc'!A0", "molar_amount": 90.0}]
}
SAMPLE = {
    "id": 7,
    "name": "../../../escaped",
    "fluid_type": "Gas",
    "gas_composition": COMPOSITION,
    "experiments": [
        {
            "type": "CCE",
            "name": "../../../../escaped-experiment",
            "temperature": 100.0,
            "temperature_unit": "C",
            "stages": [{"is_saturation_pressure": True, "pressure": 300.0}],
        },
        {
            "type": "CCE",
            "name": "second",
            "temperature": 120.0,
            "temperature_unit": "C",
            "stages": [{"is_saturation_pressure": False, "pressure": 200.0}],
        },
    ],
}


def _files(root):
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def test_samples_export_writes_one_directory_per_sample_inside_out(httpx2_mock, tmp_path):
    httpx2_mock.add_response(url=f"{API}/samples/7", json=SAMPLE)
    work = tmp_path / "work"
    out = work / "export"

    result = runner.invoke(app, ["samples", "export", "7", "--out", str(out), "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"samples": [{"sample_id": 7, "directory": f"{out}/7"}]}
    assert _files(work) == [
        "export/7/compositions/gas_composition.json",
        "export/7/experiments/1-CCE.json",
        "export/7/experiments/2-CCE.json",
        "export/7/index.json",
        "export/7/sample.json",
    ]
    sample_dir = out / "7"
    index = json.loads((sample_dir / "index.json").read_text())
    assert index["sample_id"] == 7
    assert index["sample_name"] == "../../../escaped"
    assert index["api_version"] == "external/v2"
    assert index["compositions"] == [
        {"field": "gas_composition", "file": "compositions/gas_composition.json"}
    ]
    assert [(e["position"], e["name"], e["file"]) for e in index["experiments"]] == [
        (1, "../../../../escaped-experiment", "experiments/1-CCE.json"),
        (2, "second", "experiments/2-CCE.json"),
    ]
    header = json.loads((sample_dir / "sample.json").read_text())
    assert header["fluid_type"] == "Gas"
    assert "gas_composition" not in header and "experiments" not in header
    composition = json.loads((sample_dir / "compositions/gas_composition.json").read_text())
    assert composition["components"][0]["molar_amount"] == 90.0
    experiment = json.loads((sample_dir / "experiments/2-CCE.json").read_text())
    assert experiment["stages"][0]["pressure"] == 200.0


def test_samples_export_refuses_a_non_empty_directory_unless_forced(httpx2_mock, tmp_path):
    occupied = tmp_path / "7"
    occupied.mkdir()
    (occupied / "notes.txt").write_text("mine")

    refused = runner.invoke(app, ["samples", "export", "7", "--out", str(tmp_path)])

    assert refused.exit_code == 2
    assert "--force" in refused.stderr
    assert httpx2_mock.get_requests() == []
    assert (occupied / "notes.txt").read_text() == "mine"

    httpx2_mock.add_response(url=f"{API}/samples/7", json=SAMPLE)
    forced = runner.invoke(app, ["samples", "export", "7", "--out", str(tmp_path), "--force"])

    assert forced.exit_code == 0, forced.stderr
    assert not (occupied / "notes.txt").exists()
    assert (occupied / "index.json").exists()


BLACK_OIL_TABLE = {
    **TABLE_UNITS,
    "id": 5,
    "feed_composition": {"id": 1, "sample_id": None, "components": []},
    "injection_composition": None,
    "gas_expansion_factor_unit": "Sm3/m3",
    "gas_formation_volume_factor_unit": "m3/Sm3",
    "gas_viscosity_unit": "cP",
    "oil_formation_volume_factor_unit": "m3/Sm3",
    "oil_viscosity_unit": "cP",
    "pressure_unit": "bara",
    "solution_cgr_unit": "Sm3/1e6-Sm3",
    "solution_gor_unit": "Sm3/Sm3",
    "surface_process": {"id": 1, "pressure_unit": "bara", "temperature_unit": "C", "stages": []},
    "rows": [
        {
            "black_oil_table_id": 5,
            "id": row_id,
            "pressure": pressure,
            "gas_expansion_factor": 100.0,
            "gas_formation_volume_factor": 0.01,
            "gas_viscosity": 0.02,
            "is_extrapolated": False,
            "oil_formation_volume_factor": 1.5,
            "oil_viscosity": 0.3,
            "solution_cgr": 50.0,
            "solution_gor": 120.0,
        }
        for row_id, pressure in ((1, 300.0), (2, 250.5))
    ],
}


def test_black_oil_table_export_writes_every_row_as_csv_with_units(httpx2_mock, tmp_path):
    httpx2_mock.add_response(url=f"{API}/black-oil-tables/5", json=BLACK_OIL_TABLE)
    out = tmp_path / "table.csv"

    result = runner.invoke(app, ["bot", "export", "5", "--out", str(out), "--format", "csv"])

    assert result.exit_code == 0, result.stderr
    header, *rows = out.read_text().splitlines()
    assert header.split(",")[:3] == [
        "black_oil_table_id",
        "gas_expansion_factor [Sm3/m3]",
        "gas_formation_volume_factor [m3/Sm3]",
    ]
    assert "pressure [bara]" in header.split(",")
    assert [row.split(",")[header.split(",").index("pressure [bara]")] for row in rows] == [
        "300.0",
        "250.5",
    ]


@pytest.mark.parametrize(
    ("args", "url"),
    [
        (["/regions"], f"{API}/regions"),
        (["regions"], f"{API}/regions"),
        (["GET", "/external/v2/samples/3"], f"{API}/samples/3"),
        (["get", "/import-sessions/1/records"], f"{API}/import-sessions/1/records"),
        (["https://evil.example.com/external/v2/regions"], None),
        (["//evil.example.com/regions"], None),
        (["http://dev.pvt.whitson.com.evil.example.com/regions"], None),
        (["/regions/../../internal"], None),
        (["/external/v2/../v1/regions"], None),
        (["/regions/%2e%2e/%2e%2e/internal"], None),
        (["/regions/..%2finternal"], None),
        (["/regions\\..\\internal"], None),
        (["/regions?limit=5"], None),
        (["/regions/"], None),
    ],
    ids=[
        "relative",
        "no-leading-slash",
        "prefix-stripped",
        "lower-case-method",
        "absolute-url",
        "network-path",
        "lookalike-host",
        "dot-dot",
        "dot-dot-after-prefix",
        "encoded-dot-dot",
        "encoded-slash",
        "backslash",
        "query-in-path",
        "empty-segment",
    ],
)
def test_api_stays_under_the_external_v2_prefix(httpx2_mock, args, url):
    if url is not None:
        httpx2_mock.add_response(url=url, json={"ok": True})

    result = runner.invoke(app, ["api", *args])

    if url is None:
        assert result.exit_code == 2
        assert "Refusing the path" in result.stderr
        assert httpx2_mock.get_requests() == []
    else:
        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {"ok": True}
        assert httpx2_mock.get_requests()[0].headers["Authorization"] == f"Bearer {TOKEN}"


def test_api_request_options(httpx2_mock, tmp_path):
    body = tmp_path / "body.json"
    body.write_text('{"fluid_model_id": 1}')
    httpx2_mock.add_response(
        method="POST", url=f"{API}/calculations/flash", json={"ok": 1}, is_reusable=True
    )
    httpx2_mock.add_response(
        method="PUT",
        url=f"{API}/regions/2?name=North",
        json={"id": 2},
        headers={"X-RateLimit-Remaining": "9"},
    )

    inline = runner.invoke(app, ["api", "/calculations/flash", "-d", '{"fluid_model_id": 1}'])
    from_file = runner.invoke(app, ["api", "/calculations/flash", "--data", f"@{body}"])
    put = runner.invoke(
        app, ["api", "PUT", "/regions/2", "-q", "name=North", "-d", "{}", "--include"]
    )

    assert [inline.exit_code, from_file.exit_code, put.exit_code] == [0, 0, 0]
    posts = httpx2_mock.get_requests(method="POST")
    assert [json.loads(request.content) for request in posts] == [{"fluid_model_id": 1}] * 2
    assert "HTTP 200" in put.stderr and "x-ratelimit-remaining: 9" in put.stderr
    assert TOKEN not in put.stderr


@pytest.mark.parametrize(
    "args",
    [
        ["api", "/calculations/flash", "-d", "{not json"],
        ["api", "/calculations/flash", "-d", "[1, 2]"],
        ["api", "/regions", "-q", "limit"],
        ["api", "FETCH", "/regions"],
        ["api", "POST", "/regions", "--paginate"],
        ["api", "--list", "/regions"],
        ["api"],
    ],
    ids=[
        "invalid-json",
        "not-objects",
        "query-without-value",
        "unknown-method",
        "paginate-post",
        "list-with-path",
        "nothing",
    ],
)
def test_api_refuses_bad_arguments_before_any_request(httpx2_mock, args):
    result = runner.invoke(app, args)

    assert result.exit_code == 2, result.stdout
    assert httpx2_mock.get_requests() == []


def test_api_paginate_follows_the_cursor_into_one_document(httpx2_mock, tmp_path):
    httpx2_mock.add_response(
        url=f"{API}/regions/3/wells?limit=1",
        json={**_page("wells", [{"id": 1}], "c2"), "region_id": 3},
    )
    httpx2_mock.add_response(
        url=f"{API}/regions/3/wells?limit=1&cursor=c2", json=_page("wells", [{"id": 2}], "c3")
    )
    httpx2_mock.add_response(
        url=f"{API}/regions/3/wells?limit=1&cursor=c3", json=_page("wells", [{"id": 3}])
    )
    out = tmp_path / "wells.json"

    result = runner.invoke(
        app, ["api", "/regions/3/wells", "-q", "limit=1", "--paginate", "--out", str(out)]
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(out.read_text()) == {
        "region_id": 3,
        "wells": [{"id": 1}, {"id": 2}, {"id": 3}],
        "pagination": {"next_cursor": None, "prev_cursor": None},
    }


def test_api_paginate_refuses_a_response_without_a_cursor(httpx2_mock):
    httpx2_mock.add_response(url=f"{API}/samples/3", json={"id": 3, "experiments": []})

    result = runner.invoke(app, ["api", "/samples/3", "--paginate"])

    assert result.exit_code == 2
    assert "without --paginate" in result.stderr
    assert result.stdout == ""


OPENAPI = {
    "openapi": "3.1.0",
    "x-unknown": {"ignored": True},
    "paths": {
        "/samples/{sample_id}": {
            "parameters": [{"$ref": "#/components/parameters/Shared"}],
            "get": {
                "summary": "Get a sample",
                "security": [{"m2m_auth": []}, {"api_token": ["samples:read"]}],
                "parameters": [
                    {
                        "name": "sample_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/GetSampleModel"}
                            }
                        }
                    },
                },
            },
        },
        "/calculations/flash": {
            "post": {
                "summary": "Flash",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/FlashCalculationRequestModel"}
                        }
                    }
                },
                "responses": {"200": {"description": "ok"}},
            }
        },
    },
}


def test_api_lists_and_describes_routes_from_the_openapi_document(httpx2_mock):
    httpx2_mock.add_response(url=f"{API}/docs/openapi.json", json=OPENAPI, is_reusable=True)

    listed = runner.invoke(app, ["api", "--list", "--json"])
    described = runner.invoke(app, ["api", "--describe", "GET", "/external/v2/samples/12"])
    described_json = runner.invoke(app, ["api", "--describe", "/calculations/flash", "--json"])
    missing = runner.invoke(app, ["api", "--describe", "DELETE", "/samples/12"])

    assert listed.exit_code == 0, listed.stderr
    assert json.loads(listed.stdout) == {
        "routes": [
            {"method": "POST", "path": "/calculations/flash", "summary": "Flash"},
            {"method": "GET", "path": "/samples/{sample_id}", "summary": "Get a sample"},
        ]
    }
    assert described.stdout.splitlines() == [
        "GET /samples/{sample_id}",
        "  Get a sample",
        "  scopes: samples:read",
        "  path sample_id (integer, required)",
        "  request: -",
        "  response 200: GetSampleModel",
    ]
    assert json.loads(described_json.stdout)["routes"][0]["request_schema"] == (
        "FlashCalculationRequestModel"
    )
    assert missing.exit_code == 2
    assert "wpvt api --list" in missing.stderr


OUTPUT_UNITS = {
    "pressure": "bara",
    "temperature": "C",
    "density": "kg/m3",
    "viscosity": "cP",
    "oil_volume": "m3",
    "gas_volume": "Sm3",
    "solution_gas_oil_ratio": "Sm3/m3",
    "solution_oil_gas_ratio": "m3/Sm3",
    "oil_formation_volume_factor": "m3/Sm3",
    "gas_formation_volume_factor": "m3/Sm3",
    "viscosibility": "1/bar",
    "compressibility": "1/bar",
    "thermal_expansion_coefficient": "1/K",
    "bulk_modulus": "bar",
    "molar_enthalpy": "J/mol",
    "specific_enthalpy": "J/kg",
    "molar_entropy": "J/(mol*K)",
    "specific_entropy": "J/(kg*K)",
    "molar_heat_capacity": "J/(mol*K)",
    "specific_heat_capacity": "J/(kg*K)",
    "joule_thomson_coefficient": "K/bar",
    "speed_of_sound": "m/s",
    "thermal_conductivity": "W/(m*K)",
}
ERROR_ROW = {"status": "error", "error": {"code": "calculation_failed", "message": "bad row"}}
FLASH_RESPONSE = {"output_unit_system": "SI", "output_units": OUTPUT_UNITS, "results": [ERROR_ROW]}
FEED = [
    {"component_name": "C1", "molar_amount": 0.9},
    {"component_name": "C2", "molar_amount": 0.1},
]


def test_calc_flash_from_an_input_file(httpx2_mock, tmp_path):
    request = {
        "fluid_model_id": 1,
        "pressure_unit": "bara",
        "temperature_unit": "C",
        "inputs": [{"pressure": 100.0, "temperature": 80.0, "feed_composition": FEED}],
    }
    path = tmp_path / "flash.json"
    path.write_text(json.dumps(request))
    out = tmp_path / "result.json"
    httpx2_mock.add_response(method="POST", url=f"{API}/calculations/flash", json=FLASH_RESPONSE)

    result = runner.invoke(app, ["calc", "flash", "--input", str(path), "--out", str(out)])

    assert result.exit_code == 0, result.stderr
    assert json.loads(httpx2_mock.get_requests()[0].content) == request
    assert json.loads(out.read_text())["results"][0]["status"] == "error"


def test_calc_flash_from_a_stored_sample_fills_the_feed(httpx2_mock, tmp_path):
    conditions = tmp_path / "conditions.json"
    conditions.write_text(
        json.dumps(
            {
                "pressure_unit": "bara",
                "temperature_unit": "C",
                "inputs": [
                    {"pressure": 100.0, "temperature": 80.0},
                    {"pressure": 50.0, "temperature": 80.0},
                ],
            }
        )
    )
    httpx2_mock.add_response(
        method="POST",
        url=f"{API}/calculations/sample-to-eos-slate-conversion",
        json={
            "results": [
                {
                    "status": "success",
                    "result": {
                        "component_names": ["C1", "C2"],
                        "composition": FEED,
                        "mass_fractions": [0.8, 0.2],
                        "mole_fractions": [0.9, 0.1],
                    },
                }
            ]
        },
    )
    httpx2_mock.add_response(method="POST", url=f"{API}/calculations/flash", json=FLASH_RESPONSE)

    result = runner.invoke(
        app,
        ["calc", "flash", "--sample", "7", "--fluid-model", "1", "--input", str(conditions)],
    )

    assert result.exit_code == 0, result.stderr
    conversion, flash = (json.loads(request.content) for request in httpx2_mock.get_requests())
    assert conversion == {"fluid_model_id": 1, "sample_ids": [7]}
    assert flash["fluid_model_id"] == 1
    assert [entry["feed_composition"] for entry in flash["inputs"]] == [FEED, FEED]
    assert json.loads(result.stdout)["output_unit_system"] == "SI"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "--input FILE, or --sample ID --fluid-model ID"),
        (["--sample", "7"], "--sample and --fluid-model go together"),
        (["--input", "x.json", "--fluid-model", "1"], "--sample and --fluid-model go together"),
        (["--input", "x.json", "--source", "adjusted_compositions"], "--source applies only"),
    ],
    ids=["nothing", "sample-alone", "fluid-model-without-sample", "source-without-sample"],
)
def test_calc_request_options_are_exclusive(httpx2_mock, args, message):
    result = runner.invoke(app, ["calc", "phase-envelope", *args])

    assert result.exit_code == 2
    assert message in result.stderr
    assert httpx2_mock.get_requests() == []


def test_calc_with_a_sample_refuses_a_feed_or_fluid_model_in_the_file(httpx2_mock, tmp_path):
    path = tmp_path / "conditions.json"
    path.write_text(json.dumps({"fluid_model_id": 2, "inputs": [{}]}))

    result = runner.invoke(
        app, ["calc", "phase-envelope", "--sample", "7", "--fluid-model", "1", "--input", str(path)]
    )

    assert result.exit_code == 2
    assert "fluid_model_id" in result.stderr
    assert httpx2_mock.get_requests() == []

"""Copy PVT reports from multiple source domains into a single target domain.

Reads a JSON config file that specifies source domains (each with its own
credentials and report IDs) and a target domain.  For each report the script
exports the zip archive from the source, runs an import preflight against
the target, and --- if the preflight clears --- commits the import.

Reports from each source are processed concurrently (configurable via
``max_workers``, defaults to 1 = sequential).

Usage::

    uv run examples/multi_domain_copy.py multi_domain_config.json

The JSON Schema for the config file is at ``config/multi_domain_config.schema.json``.
Generate an updated copy with::

    uv run examples/multi_domain_copy.py --schema
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import ValidationError

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import (
    ClientCredentials,
    DomainAuthConfig,
    ImportArchiveOptions,
    MultiDomainCopyConfig,
    SourceDomainConfig,
)
from whitson_pvt_sdk.v1 import WhitsonPVTClientV1
from whitson_pvt_sdk.v1.models import CreateRegionModel as CreateRegionModelV1
from whitson_pvt_sdk.v2.models import CreateRegionModel as CreateRegionModelV2


def _build_region_map(
    target: WhitsonPVTClient,  # type: ignore[valid-type]
    config: MultiDomainCopyConfig,
) -> dict[str, int]:
    region_map: dict[str, int] = {}
    all_regions: list = []

    if isinstance(target, WhitsonPVTClientV1):
        page = target.regions.list()
        all_regions = list(page.regions)
    else:
        page = target.regions.list(limit=250)
        all_regions = list(page.regions)
        while page.pagination.next_cursor:
            page = target.regions.list(cursor=page.pagination.next_cursor, limit=250)
            all_regions.extend(page.regions)

    for region in all_regions:
        if region.name:
            region_map[region.name] = region.id

    for spec in config.create_regions:
        if spec.name not in region_map:
            create_model = (
                CreateRegionModelV1
                if isinstance(target, WhitsonPVTClientV1)
                else CreateRegionModelV2
            )
            created = target.regions.create(
                create_model(**spec.model_dump(exclude_none=True))
            )
            if created.name:
                region_map[created.name] = created.id
                print(f"Created region: {created.name} (id={created.id})")

    return region_map


def _resolve_region_id(
    src: SourceDomainConfig,
    config: MultiDomainCopyConfig,
    region_map: dict[str, int],
) -> int | None:
    if src.target_region_id is not None:
        return src.target_region_id
    if src.target_region_name is not None:
        rid = region_map.get(src.target_region_name)
        if rid is not None:
            return rid
        print(
            f"WARNING [{src.domain}]: target_region_name "
            f"'{src.target_region_name}' not found in target — "
            "will import without a region_id",
            file=sys.stderr,
        )
        return None
    return config.target_region_id


def _build_opts(
    src: SourceDomainConfig,
    config: MultiDomainCopyConfig,
    region_map: dict[str, int],
) -> ImportArchiveOptions:
    region_id = _resolve_region_id(src, config, region_map)
    ack = (
        src.acknowledge_suggestions
        if src.acknowledge_suggestions is not None
        else config.acknowledge_suggestions
    )
    return ImportArchiveOptions(region_id=region_id, acknowledge_suggestions=ack)


def _copy_one_report(
    domain_auth: DomainAuthConfig,
    import_opts: ImportArchiveOptions,
    target: WhitsonPVTClient,  # type: ignore[valid-type]
    domain: str,
    report_id: int,
) -> tuple[int, str, str]:
    source = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=domain_auth.client_id,
            client_secret=domain_auth.client_secret,
        ),
        base_url=domain_auth.base_url,
        version=domain_auth.version,
        retry_config=domain_auth.retry_config,
    )
    try:
        zip_data, _filename = source.reports.export(report_id)
        preflight = target.reports.preflight_import(zip_data, import_opts)
        if preflight.can_commit:
            result = target.reports.import_archive(zip_data, import_opts)
            return (
                report_id,
                "ok",
                f"created={result.created}  reused={result.reused}",
            )
        else:
            cols = len(preflight.collisions)
            suggs = len(preflight.suggestions)
            return (
                report_id,
                "collision",
                f"collisions={cols}  suggestions={suggs}",
            )
    except Exception as exc:
        return (report_id, "error", str(exc))


def _run(config: MultiDomainCopyConfig) -> int:
    target = WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=config.target.client_id,
            client_secret=config.target.client_secret,
        ),
        base_url=config.target.base_url,
        version=config.target.version,
        retry_config=config.target.retry_config,
    )

    region_map = _build_region_map(target, config)

    total_ok = 0
    total_skipped = 0
    total_error = 0

    for src in config.sources:
        import_opts = _build_opts(src, config, region_map)
        domain_auth = config.domain_configs[src.domain]
        ok = 0
        skipped = 0
        errors = 0

        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            futures = {
                executor.submit(
                    _copy_one_report,
                    domain_auth,
                    import_opts,
                    target,
                    src.domain,
                    rid,
                ): rid
                for rid in src.report_ids
            }
            for future in as_completed(futures):
                rid, status, detail = future.result()
                tag = f"[{src.domain}] report {rid}"
                if status == "ok":
                    print(f"{tag}: OK  {detail}")
                    ok += 1
                elif status == "collision":
                    print(f"{tag}: COLLISION  {detail}")
                    skipped += 1
                else:
                    print(f"{tag}: ERROR  {detail}")
                    errors += 1

        print(f"[{src.domain}] summary: {ok} ok, {skipped} skipped, {errors} errors")
        total_ok += ok
        total_skipped += skipped
        total_error += errors

    print(f"Total: {total_ok} ok, {total_skipped} skipped, {total_error} errors")
    return 1 if total_error else 0


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: uv run examples/multi_domain_copy.py <config.json>")
        print("       uv run examples/multi_domain_copy.py --schema")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "--schema":
        schema = MultiDomainCopyConfig.model_json_schema()
        print(json.dumps(schema, indent=2))
        return

    try:
        raw = json.loads(Path(arg).read_text())
        config = MultiDomainCopyConfig.model_validate(raw)
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        print(f"Error reading config file: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as exc:
        print(f"Config validation error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(_run(config))


if __name__ == "__main__":
    main()

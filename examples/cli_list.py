"""CLI for listing SDK resources.

Demonstrates:
- argparse-based CLI built on the SDK
- Subcommands for different resource types
- Environment variable credentials
- Human-readable output

Usage:
    uv run examples/cli_list.py regions
    uv run examples/cli_list.py wells --region-id 1
    uv run examples/cli_list.py projects --region-id 1
    uv run examples/cli_list.py samples --well-id 1
"""

import argparse
import os
import sys

from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.models.manual import ClientCredentials
from whitson_pvt_sdk.v2 import WhitsonPVTClientV2


def get_client() -> WhitsonPVTClientV2:
    return WhitsonPVTClient(
        credentials=ClientCredentials(
            client_id=os.environ["WHITSON_CLIENT_ID"],
            client_secret=os.environ["WHITSON_CLIENT_SECRET"],
        ),
        base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
    )


def cmd_regions(args: argparse.Namespace) -> None:
    client = get_client()
    page = client.regions.list(limit=args.limit)
    for region in page.regions:
        print(f"{region.id:>6}  {region.name}")


def cmd_wells(args: argparse.Namespace) -> None:
    client = get_client()
    page = client.wells.list(region_id=args.region_id, limit=args.limit)
    for well in page.wells:
        print(f"{well.id:>6}  {well.name}")
    if page.pagination.next_cursor:
        print(f"next_cursor={page.pagination.next_cursor}")


def cmd_projects(args: argparse.Namespace) -> None:
    client = get_client()
    page = client.projects.list(region_id=args.region_id, limit=args.limit)
    for project in page.projects:
        print(f"{project.id:>6}  {project.name}")


def cmd_samples(args: argparse.Namespace) -> None:
    client = get_client()
    samples = client.samples.list(well_id=args.well_id)
    for sample in samples.samples:
        assert sample.id is not None
        types = client.samples.experiment_types(sample_id=sample.id)
        print(f"{sample.id:>6}  {sample.name:30s}  experiments={types}")


def cmd_fluid_models(args: argparse.Namespace) -> None:
    client = get_client()
    page = client.fluid_models.list(project_id=args.project_id, limit=args.limit)
    for fm in page.fluid_models:
        print(f"{fm.id:>6}  {fm.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="List whitson PVT resources")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("regions", help="List all regions")

    p = sub.add_parser("wells", help="List wells in a region")
    p.add_argument("--region-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=None)

    p = sub.add_parser("projects", help="List projects in a region")
    p.add_argument("--region-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=None)

    p = sub.add_parser("samples", help="List samples in a well")
    p.add_argument("--well-id", type=int, required=True)

    p = sub.add_parser("fluid-models", help="List fluid models in a project")
    p.add_argument("--project-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=None)

    parser.set_defaults(limit=None)

    args = parser.parse_args()

    try:
        {
            "regions": cmd_regions,
            "wells": cmd_wells,
            "projects": cmd_projects,
            "samples": cmd_samples,
            "fluid-models": cmd_fluid_models,
        }[args.command](args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

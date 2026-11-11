"""CLI for listing SDK resources.

Demonstrates:
- argparse-based CLI built on the SDK
- Subcommands for different resource types
- API token from the PVT_TOKEN environment variable
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

from dotenv import load_dotenv

from whitson_pvt_sdk import WhitsonPVTClient

load_dotenv()


def cmd_regions(client: WhitsonPVTClient, args: argparse.Namespace) -> None:
    page = client.regions.list(limit=args.limit)
    for region in page.regions:
        print(f"{region.id:>6}  {region.name}")


def cmd_wells(client: WhitsonPVTClient, args: argparse.Namespace) -> None:
    page = client.wells.list(region_id=args.region_id, limit=args.limit)
    for well in page.wells:
        print(f"{well.id:>6}  {well.name}")
    if page.pagination.next_cursor:
        print(f"next_cursor={page.pagination.next_cursor}")


def cmd_projects(client: WhitsonPVTClient, args: argparse.Namespace) -> None:
    page = client.projects.list(region_id=args.region_id, limit=args.limit)
    for project in page.projects:
        print(f"{project.id:>6}  {project.name}")


def cmd_samples(client: WhitsonPVTClient, args: argparse.Namespace) -> None:
    samples = client.samples.list(well_id=args.well_id)
    for sample in samples.samples:
        assert sample.id is not None
        experiment_count = len(sample.experiments or [])
        print(f"{sample.id:>6}  {sample.name:30s}  experiments={experiment_count}")


def cmd_fluid_models(client: WhitsonPVTClient, args: argparse.Namespace) -> None:
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
        with WhitsonPVTClient(
            base_url=os.environ.get("WHITSON_BASE_URL", "https://internal.pvt.whitson.com"),
        ) as client:
            {
                "regions": cmd_regions,
                "wells": cmd_wells,
                "projects": cmd_projects,
                "samples": cmd_samples,
                "fluid-models": cmd_fluid_models,
            }[args.command](client, args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

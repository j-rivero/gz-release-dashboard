"""Command line entry point: ``fetch`` writes a snapshot, the rest render it."""

from __future__ import annotations

import click

from . import __version__, config, ground_truth, snapshot as snap
from .collections_yaml import load_collections
from .http import HttpClient
from .models import FetchError
from .sources import available_sources, create_sources


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="gz-dashboard")
def main() -> None:
    """Track Gazebo library versions across every packaging system."""


def _collect(
    sources: tuple[str, ...],
    collection_filter: tuple[str, ...],
    cache_dir: str | None,
):
    """Fetch the ground truth and every selected source into a snapshot."""
    http = HttpClient(cache_dir=cache_dir)
    collections = load_collections(http)
    if collection_filter:
        wanted = set(collection_filter)
        collections = [c for c in collections if c.name in wanted]
        if not collections:
            raise click.ClickException(
                f"no collection matched {', '.join(sorted(wanted))}"
            )

    instances = create_sources(list(sources) or None, http)
    snapshot = snap.new_snapshot([s.name for s in instances])
    snapshot.collections = collections

    click.echo(f"ground truth: {len(collections)} collections", err=True)
    entries, errors = ground_truth.build_ground_truth(collections)
    snapshot.ground_truth = entries
    snapshot.errors.extend(errors)

    failures = 0
    for source in instances:
        click.echo(f"fetching {source.name}...", err=True)
        try:
            snapshot.records.extend(source.fetch(collections))
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the run
            failures += 1
            snapshot.errors.append(FetchError(source.name, f"{type(exc).__name__}: {exc}"))
            click.echo(f"  {source.name} failed: {exc}", err=True)
    if instances and failures == len(instances):
        raise click.ClickException("every source failed; refusing to write a snapshot")
    return snapshot


@main.command()
@click.option(
    "-o", "--output", default="snapshot.json", show_default=True,
    type=click.Path(dir_okay=False), help="Where to write the snapshot.",
)
@click.option(
    "--source", "sources", multiple=True, type=click.Choice(available_sources()),
    help="Fetch only these sources (repeatable).",
)
@click.option(
    "--collection", "collections_", multiple=True,
    help="Fetch only these collections (repeatable).",
)
@click.option(
    "--cache-dir", type=click.Path(file_okay=False),
    help="Memoise HTTP bodies here; handy while iterating.",
)
def fetch(output, sources, collections_, cache_dir):
    """Query every source and write a JSON snapshot."""
    snapshot = _collect(sources, collections_, cache_dir)
    path = snap.save(snapshot, output)
    click.echo(
        f"wrote {path}: {len(snapshot.records)} records, "
        f"{len(snapshot.errors)} errors",
        err=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()

"""Command line entry point: ``fetch`` writes a snapshot, the rest render it."""

from __future__ import annotations

import click

from rich.console import Console

from . import __version__, engine, ground_truth, snapshot as snap
from .collections_yaml import load_collections
from .http import HttpClient
from .models import FetchError, Snapshot, StatusEntry
from .render import console as console_render, html as html_render
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


def _filtered(
    snapshot: Snapshot,
    collections_: tuple[str, ...],
    sources: tuple[str, ...],
    libs: tuple[str, ...],
) -> tuple[Snapshot, list[StatusEntry]]:
    """Narrow a loaded snapshot, then compute the statuses of what is left."""
    if collections_:
        wanted = set(collections_)
        snapshot.collections = [c for c in snapshot.collections if c.name in wanted]
    if sources:
        keep = set(sources)
        snapshot.sources_fetched = [s for s in snapshot.sources_fetched if s in keep]
        snapshot.records = [r for r in snapshot.records if r.source in keep]
    if libs:
        names = set(libs)
        for collection in snapshot.collections:
            collection.libraries = [l for l in collection.libraries if l.name in names]
    return snapshot, engine.compute_statuses(snapshot)


_filter_options = [
    click.option("--collection", "collections_", multiple=True,
                 help="Show only these collections (repeatable)."),
    click.option("--source", "sources", multiple=True,
                 type=click.Choice(available_sources()),
                 help="Show only these sources (repeatable)."),
    click.option("--lib", "libs", multiple=True,
                 help="Show only these libraries (repeatable)."),
]


def add_filter_options(command):
    for option in reversed(_filter_options):
        command = option(command)
    return command


@main.command(name="console")
@click.argument("snapshot_path", metavar="[SNAPSHOT]", default="snapshot.json",
                type=click.Path(exists=True, dir_okay=False))
@add_filter_options
@click.option("--problems-only", is_flag=True, help="Print only the problems panel.")
@click.option("--verbose", is_flag=True, help="Add a per-platform detail table.")
@click.option("--fail-on-problems", is_flag=True,
              help="Exit non-zero when anything is behind or missing.")
def console_cmd(snapshot_path, collections_, sources, libs, problems_only, verbose,
                fail_on_problems):
    """Render a snapshot as a colourful terminal dashboard."""
    snapshot, entries = _filtered(snap.load(snapshot_path), collections_, sources, libs)
    count = console_render.render(
        snapshot, entries, Console(), verbose=verbose, problems_only=problems_only
    )
    if fail_on_problems and count:
        raise SystemExit(1)


@main.command(name="html")
@click.argument("snapshot_path", metavar="[SNAPSHOT]", default="snapshot.json",
                type=click.Path(exists=True, dir_okay=False))
@add_filter_options
@click.option("-o", "--output", "out_dir", default="public", show_default=True,
              type=click.Path(file_okay=False),
              help="Directory to write index.html and snapshot.json into.")
def html_cmd(snapshot_path, collections_, sources, libs, out_dir):
    """Render a snapshot as a static page for GitHub Pages."""
    snapshot, entries = _filtered(snap.load(snapshot_path), collections_, sources, libs)
    path = html_render.write(snapshot, entries, out_dir)
    click.echo(f"wrote {path}", err=True)


@main.command(name="all")
@click.option("-o", "--output", "out_dir", default="public", show_default=True,
              type=click.Path(file_okay=False), help="Directory to publish into.")
@click.option("--source", "sources", multiple=True, type=click.Choice(available_sources()),
              help="Fetch only these sources (repeatable).")
@click.option("--collection", "collections_", multiple=True,
              help="Fetch only these collections (repeatable).")
@click.option("--cache-dir", type=click.Path(file_okay=False),
              help="Memoise HTTP bodies here; handy while iterating.")
@click.option("--fail-on-problems", is_flag=True,
              help="Exit non-zero when anything is behind or missing.")
def all_cmd(out_dir, sources, collections_, cache_dir, fail_on_problems):
    """Fetch, report the problems on stderr, and publish the page."""
    snapshot = _collect(sources, collections_, cache_dir)
    entries = engine.compute_statuses(snapshot)
    count = console_render.render(
        snapshot, entries, Console(stderr=True), problems_only=True
    )
    path = html_render.write(snapshot, entries, out_dir)
    click.echo(f"wrote {path}", err=True)
    if fail_on_problems and count:
        raise SystemExit(1)

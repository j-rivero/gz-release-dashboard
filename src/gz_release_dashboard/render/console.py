"""Rich console rendering: one table per collection plus a problems panel."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..deps.inventory import DependencyRow, dependency_rows
from ..engine import SEVERITY
from ..models import Snapshot, Status, StatusEntry
from . import (
    DIVERGE_GLYPH,
    DIVERGE_LABEL,
    STATUS_GLYPHS,
    WARN_GLYPH,
    WARN_LABEL,
    group_problems,
    STATUS_LABELS,
    STATUS_STYLES,
    aggregate_cell,
    column_order,
    dependency_columns,
    dependency_label,
    group_cells,
    source_label,
)

WARN_STYLE = "yellow"
DIVERGE_STYLE = "cyan"


def _column_header(source: str, channel: str) -> str:
    # Always two lines, so a channel-less source's name never lands in the row
    # where the reader is looking for channels.
    return f"{source_label(source)}\n{channel or '(all)'}"


def _cell_text(cell) -> Text:
    if cell is None:
        return Text("·", style="dim")
    style = STATUS_STYLES[cell.status]
    text = Text(f"{cell.glyph} ", style=style)
    text.append(cell.version or STATUS_LABELS[cell.status], style=style)
    if cell.status is Status.BEHIND and cell.expected:
        text.append(f"\n→ {cell.expected}", style="dim")
    if cell.mixed:
        text.append(f" ({cell.worst_count}/{cell.total})", style="dim")
    return text


def collection_table(collection_name: str, in_development: bool, columns, grouped) -> Table:
    # A Text object, not markup: "[in development]" would be parsed as a tag.
    title = Text(collection_name, style="bold")
    if in_development:
        title.append("  [in development]", style="dim not bold")
    table = Table(title=title, title_justify="left", header_style="bold", expand=False)
    table.add_column("library", style="bold")
    for source, channel in columns:
        table.add_column(_column_header(source, channel), justify="left")
    libraries = sorted({(k[1], k[2]) for k in grouped if k[0] == collection_name})
    for library, major in libraries:
        row = [Text(f"{library} ({major})")]
        for source, channel in columns:
            entries = grouped.get((collection_name, library, major, source, channel), [])
            row.append(_cell_text(aggregate_cell(entries)))
        table.add_row(*row)
    return table


def dependency_table(rows: list[DependencyRow], systems: list[str]) -> Table:
    """What one collection's builds declare, one column per build system."""
    table = Table(
        title=Text("dependencies", style="dim"), title_justify="left",
        header_style="bold", expand=False,
    )
    table.add_column("dependency", style="bold")
    for system in systems:
        table.add_column(dependency_label(system), justify="left")
    for row in rows:
        name = Text(row.dependency)
        if row.diverges:
            name.append(f" {DIVERGE_GLYPH}", style=DIVERGE_STYLE)
        cells = [name]
        for system in systems:
            cell = row.cells.get(system)
            if cell is None:
                cells.append(Text("·", style="dim"))
                continue
            # A label or "?" is not a version; dimming it keeps it from reading as one.
            text = Text(cell.text, style="" if cell.versions else "dim")
            if cell.warn:
                text.append(f" {WARN_GLYPH}", style=WARN_STYLE)
            cells.append(text)
        table.add_row(*cells)
    return table


def detail_table(entries: list[StatusEntry]) -> Table:
    """Every platform/arch that is not simply up to date."""
    table = Table(title="details", title_justify="left", header_style="bold")
    for column in ("collection", "library", "source", "channel", "platform", "arch",
                   "found", "expected", "status"):
        table.add_column(column)
    interesting = [e for e in entries if e.status is not Status.UP_TO_DATE]
    for entry in sorted(
        interesting,
        key=lambda e: (-SEVERITY[e.status], e.collection, e.library, e.source, e.platform),
    ):
        table.add_row(
            entry.collection,
            f"{entry.library} ({entry.major})",
            source_label(entry.source),
            entry.channel or "-",
            entry.platform,
            entry.arch,
            entry.found_version or "-",
            entry.expected_version or "-",
            Text(
                f"{STATUS_GLYPHS[entry.status]} {STATUS_LABELS[entry.status]}",
                style=STATUS_STYLES[entry.status],
            ),
        )
    return table


def dependency_detail_table(rows: list[DependencyRow]) -> Table:
    """Every declaration, with the platforms that agree on it on one line.

    A deb dependency is one record per distribution and architecture; listing
    them one by one would bury the line that differs.
    """
    table = Table(title="dependency details", title_justify="left", header_style="bold")
    for column in ("collection", "dependency", "system", "library", "declared",
                   "version", "origin", "platforms"):
        # Folded, never cut short: the declared pin and the platform list are
        # what explain a mark, and an ellipsis hides exactly the part that differs.
        table.add_column(column, overflow="fold" if column in {"declared", "platforms"} else "ellipsis")
    for row in rows:
        for system, cell in sorted(row.cells.items()):
            lines: dict[tuple[str, str, str, str], list[str]] = {}
            for record in cell.records:
                key = (
                    f"{record.library}{record.major}",
                    record.declared,
                    record.version or record.label or "?",
                    record.origin or "-",
                )
                lines.setdefault(key, []).append(record.platform)
            for (library, declared, version, origin), platforms in sorted(lines.items()):
                table.add_row(
                    row.collection, row.dependency, dependency_label(system), library,
                    declared, version, origin, ", ".join(sorted(platforms)),
                )
    return table


def _problem_line(problem) -> Text:
    channel = f" {problem.channel}" if problem.channel else ""
    text = Text(f"{problem.glyph} ", style=STATUS_STYLES[problem.status])
    text.append(f"{problem.title} ")
    if problem.status is Status.BEHIND:
        text.append(f"{problem.found} < {problem.expected} ")
    else:
        text.append("missing ")
    text.append(f"in {source_label(problem.source)}{channel}", style="dim")
    text.append(f" — {problem.where(limit=4)}", style="dim")
    return text


def problems_panel(entries: list[StatusEntry], limit: int = 40) -> Panel:
    found = group_problems(entries)
    if not found:
        return Panel(Text("✅ every source matches the latest release", style="green"),
                     title="problems", title_align="left", border_style="green")
    body = Text("\n").join(_problem_line(p) for p in found[:limit])
    if len(found) > limit:
        body.append(f"\n… and {len(found) - limit} more", style="dim")
    total = sum(len(p.places) for p in found)
    title = f"problems ({len(found)})"
    if total != len(found):
        title = f"problems ({len(found)}, {total} platform cells)"
    return Panel(body, title=title, title_align="left", border_style="red")


def legend(dependencies: bool = False) -> Text:
    """The status glyphs, and the dependency marks when there is something to mark."""
    text = Text("legend: ", style="dim")
    for status, glyph in STATUS_GLYPHS.items():
        text.append(f"{glyph} {STATUS_LABELS[status]}  ", style=STATUS_STYLES[status])
    if dependencies:
        text.append(f"{WARN_GLYPH} {WARN_LABEL}  ", style=WARN_STYLE)
        text.append(f"{DIVERGE_GLYPH} {DIVERGE_LABEL}  ", style=DIVERGE_STYLE)
    return text


def render(
    snapshot: Snapshot,
    entries: list[StatusEntry],
    console: Console,
    *,
    verbose: bool = False,
    problems_only: bool = False,
    rows: list[DependencyRow] | None = None,
) -> int:
    """Print the dashboard; return the number of affected platform cells.

    ``rows`` are the dependency rows to draw, marks already settled on the
    whole snapshot; without them they are worked out from this one. Nothing
    about dependencies reaches the returned count.
    """
    if rows is None:
        rows = dependency_rows(snapshot.dependencies)
    if not problems_only:
        console.print(
            Text(
                f"Gazebo release dashboard — snapshot {snapshot.generated_at} "
                f"(tool {snapshot.tool_version})",
                style="bold",
            )
        )
        console.print(legend(dependencies=bool(rows)))
        grouped = group_cells(entries)
        for collection in snapshot.collections:
            if not any(k[0] == collection.name for k in grouped):
                continue
            # Per collection, not once for the run: the sources that publish
            # fortress are not the ones that publish jetty.
            columns = column_order(snapshot.sources_fetched, collection.name)
            console.print()
            console.print(
                collection_table(collection.name, collection.in_development, columns, grouped)
            )
            systems = dependency_columns(snapshot.sources_fetched, collection.name)
            declared = [
                row for row in rows
                if row.collection == collection.name and any(s in row.cells for s in systems)
            ]
            if declared:
                console.print(dependency_table(declared, systems))
        if verbose:
            console.print()
            console.print(detail_table(entries))
            if rows:
                console.print()
                console.print(dependency_detail_table(rows))
    console.print()
    console.print(problems_panel(entries))
    if snapshot.errors:
        console.print()
        console.print(
            Panel(
                Text("\n").join(
                    Text(f"{e.source}: {e.message}") for e in snapshot.errors
                ),
                title=f"fetch errors ({len(snapshot.errors)})",
                title_align="left",
                border_style="yellow",
            )
        )
    return sum(len(p.places) for p in group_problems(entries))

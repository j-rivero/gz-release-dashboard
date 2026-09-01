"""Rich console rendering: one table per collection plus a problems panel."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..engine import SEVERITY, problems
from ..models import Snapshot, Status, StatusEntry
from . import (
    STATUS_GLYPHS,
    STATUS_LABELS,
    STATUS_STYLES,
    aggregate_cell,
    column_order,
    group_cells,
    source_label,
)


def _column_header(source: str, channel: str) -> str:
    return f"{source_label(source)}\n{channel}" if channel else source_label(source)


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


def _problem_line(entry: StatusEntry) -> Text:
    where = f"{entry.platform}/{entry.arch}" if entry.arch else entry.platform
    channel = f" {entry.channel}" if entry.channel else ""
    text = Text(f"{STATUS_GLYPHS[entry.status]} ", style=STATUS_STYLES[entry.status])
    text.append(f"{entry.collection}/{entry.library}{entry.major} ")
    if entry.status is Status.BEHIND:
        text.append(f"{entry.found_version} < {entry.expected_version} ")
    else:
        text.append("missing ")
    text.append(f"in {source_label(entry.source)}{channel} ({where})", style="dim")
    return text


def problems_panel(entries: list[StatusEntry], limit: int = 60) -> Panel:
    found = sorted(
        problems(entries),
        key=lambda e: (-SEVERITY[e.status], e.collection, e.library, e.source, e.platform),
    )
    if not found:
        return Panel(Text("✅ every source matches the latest release", style="green"),
                     title="problems", title_align="left", border_style="green")
    body = Text("\n").join(_problem_line(e) for e in found[:limit])
    if len(found) > limit:
        body.append(f"\n… and {len(found) - limit} more", style="dim")
    return Panel(body, title=f"problems ({len(found)})", title_align="left",
                 border_style="red")


def legend() -> Text:
    text = Text("legend: ", style="dim")
    for status, glyph in STATUS_GLYPHS.items():
        text.append(f"{glyph} {STATUS_LABELS[status]}  ", style=STATUS_STYLES[status])
    return text


def render(
    snapshot: Snapshot,
    entries: list[StatusEntry],
    console: Console,
    *,
    verbose: bool = False,
    problems_only: bool = False,
) -> int:
    """Print the dashboard; return the number of problems found."""
    if not problems_only:
        console.print(
            Text(
                f"Gazebo release dashboard — snapshot {snapshot.generated_at} "
                f"(tool {snapshot.tool_version})",
                style="bold",
            )
        )
        console.print(legend())
        columns = column_order(snapshot.sources_fetched)
        grouped = group_cells(entries)
        for collection in snapshot.collections:
            if not any(k[0] == collection.name for k in grouped):
                continue
            console.print()
            console.print(
                collection_table(collection.name, collection.in_development, columns, grouped)
            )
        if verbose:
            console.print()
            console.print(detail_table(entries))
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
    return len(problems(entries))

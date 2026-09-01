"""Presentation vocabulary shared by the console and HTML renderers."""

from __future__ import annotations

from dataclasses import dataclass

from ..engine import SEVERITY
from ..models import Status, StatusEntry
from ..versions import GzVersion, max_version
from ..sources import available_sources, source_class

STATUS_GLYPHS: dict[Status, str] = {
    Status.UP_TO_DATE: "✅",
    Status.BEHIND: "🔶",
    Status.MISSING: "❌",
    Status.AHEAD: "⬆️",
    Status.PRERELEASE: "🚧",
    Status.NOT_EXPECTED: "—",
}

STATUS_STYLES: dict[Status, str] = {
    Status.UP_TO_DATE: "green",
    Status.BEHIND: "yellow",
    Status.MISSING: "bold red",
    Status.AHEAD: "cyan",
    Status.PRERELEASE: "magenta",
    Status.NOT_EXPECTED: "dim",
}

STATUS_LABELS: dict[Status, str] = {
    Status.UP_TO_DATE: "up to date",
    Status.BEHIND: "behind",
    Status.MISSING: "missing",
    Status.AHEAD: "ahead",
    Status.PRERELEASE: "prerelease",
    Status.NOT_EXPECTED: "not expected",
}

SOURCE_LABELS: dict[str, str] = {
    "osrf_debian": "osrf deb",
    "conda_forge": "conda",
    "homebrew": "brew",
    "bazel_registry": "bazel",
    "ros_vendor": "ros",
}


def min_version(candidates: list[str | None]) -> str | None:
    """Lowest parseable version among ``candidates``: the one to complain about."""
    parsed = [v for v in (GzVersion.parse(c) for c in candidates) if v is not None]
    return str(min(parsed)) if parsed else None


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def column_order(sources_fetched: list[str]) -> list[tuple[str, str]]:
    """``(source, channel)`` columns, in registration order, channels expanded."""
    fetched = set(sources_fetched)
    columns: list[tuple[str, str]] = []
    for source in available_sources():
        if source not in fetched:
            continue
        for channel in source_class(source).channels or ("",):
            columns.append((source, channel))
    # Anything fetched but no longer registered still deserves a column.
    for source in sources_fetched:
        if source not in set(available_sources()):
            columns.append((source, ""))
    return columns


@dataclass
class Cell:
    """One collapsed table cell: many platforms boiled down to one verdict."""

    status: Status
    version: str | None
    expected: str | None
    worst_count: int
    total: int

    @property
    def mixed(self) -> bool:
        return self.total > 1 and self.worst_count < self.total

    @property
    def glyph(self) -> str:
        return STATUS_GLYPHS[self.status]


def aggregate_cell(entries: list[StatusEntry]) -> Cell | None:
    """Collapse every platform/arch of one (library, source, channel) into a cell.

    The worst status wins, so one missing architecture cannot hide behind eleven
    green ones, and ``mixed`` then says how many platforms are affected. Cells a
    source was never expected to fill are excluded from that ratio: they are not
    a platform that went wrong, they are a platform that does not exist.

    The version shown is the one that explains the glyph -- the *lowest* among
    the worst entries, so a BEHIND cell names the version that is behind. When
    the worst status has no version at all (MISSING), the highest version seen
    elsewhere is shown instead, so a partly-missing row still reports what the
    source does ship.
    """
    if not entries:
        return None
    relevant = [e for e in entries if e.status is not Status.NOT_EXPECTED] or entries
    status = max((e.status for e in relevant), key=lambda s: SEVERITY[s])
    worst = [e for e in relevant if e.status == status]
    worst_versions = [e.found_version for e in worst if e.found_version]
    version = (
        min_version(worst_versions)
        if worst_versions
        else max_version([e.found_version for e in relevant])
    )
    return Cell(
        status=status,
        version=version,
        expected=next((e.expected_version for e in worst if e.expected_version), None),
        worst_count=len(worst),
        total=len(relevant),
    )


def group_cells(entries: list[StatusEntry]) -> dict[tuple, list[StatusEntry]]:
    """Index entries by ``(collection, library, major, source, channel)``."""
    grouped: dict[tuple, list[StatusEntry]] = {}
    for entry in entries:
        key = (entry.collection, entry.library, entry.major, entry.source, entry.channel)
        grouped.setdefault(key, []).append(entry)
    return grouped

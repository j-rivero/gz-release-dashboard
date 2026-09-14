"""Presentation vocabulary shared by the console and HTML renderers."""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..engine import SEVERITY, problems
from ..models import Status, StatusEntry
from ..versions import GzVersion, max_version
from ..sources import available_sources, source_class

STATUS_GLYPHS: dict[Status, str] = {
    Status.UP_TO_DATE: "✅",
    Status.BEHIND: "🔶",
    Status.MISSING: "❌",
    Status.AHEAD: "⬆️",
    Status.NOT_EXPECTED: "—",
}

STATUS_STYLES: dict[Status, str] = {
    Status.UP_TO_DATE: "green",
    Status.BEHIND: "yellow",
    Status.MISSING: "bold red",
    Status.AHEAD: "cyan",
    Status.NOT_EXPECTED: "dim",
}

STATUS_LABELS: dict[Status, str] = {
    Status.UP_TO_DATE: "up to date",
    Status.BEHIND: "behind",
    Status.MISSING: "missing",
    Status.AHEAD: "ahead",
    Status.NOT_EXPECTED: "not expected",
}

SOURCE_LABELS: dict[str, str] = {
    "osrf_debian": "osrf deb",
    "conda_forge": "conda",
    "homebrew": "brew",
    "bazel_registry": "bazel",
    # Two ROS sources, so neither can be called just "ros": one is the vendor
    # package wrapping a gz library, the other the gz packages themselves in
    # the ROS Debian repositories.
    "ros_vendor": "ros vendor",
    "ros_gz_debian": "ros deb",
}


#: Build systems are named after what they build with, not after the library
#: source that reads them: a dependency lives in "deb", whichever repository
#: served it.
DEPENDENCY_LABELS: dict[str, str] = {
    "deb": "deb",
    "bazel": "bazel",
    "conda": "conda",
    "brew": "brew",
    "ros": "ros vendor",
}

WARN_GLYPH = "⚠"
DIVERGE_GLYPH = "◇"
WARN_LABEL = "a system disagrees with itself"
DIVERGE_LABEL = "systems on different series"


def dependency_label(system: str) -> str:
    return DEPENDENCY_LABELS.get(system, system)


def dependency_column_label(system: str, channel: str = "") -> str:
    return f"{dependency_label(system)} {channel}" if channel else dependency_label(system)


def dependency_columns(sources_fetched: list[str], collection: str) -> list[tuple[str, str]]:
    """The ``(system, channel)`` columns to draw for ``collection``, as the library columns are.

    Each system follows its library source, so it lands in that source's place
    and is gated by the same ``config.source_applies``: harmonic, which has no
    Bazel column for its libraries, has none for its dependencies either. A
    system read from several channels gets a column per channel, the others a
    single one with no channel.
    """
    system_of = {source: system for system, source in config.DEPENDENCY_SYSTEMS.items()}
    columns: list[tuple[str, str]] = []
    for source, _channel in column_order(sources_fetched, collection):
        system = system_of.get(source)
        if system is None or any(held == system for held, _ in columns):
            continue
        columns.extend(
            (system, channel) for channel in config.DEPENDENCY_CHANNELS.get(system, ("",))
        )
    return columns


def min_version(candidates: list[str | None]) -> str | None:
    """Lowest parseable version among ``candidates``: the one to complain about."""
    parsed = [v for v in (GzVersion.parse(c) for c in candidates) if v is not None]
    return str(min(parsed)) if parsed else None


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def column_order(
    sources_fetched: list[str], collection: str | None = None
) -> list[tuple[str, str]]:
    """``(source, channel)`` columns, in registration order, channels expanded.

    Given a collection, only the sources that publish it: fortress predates
    Bazel, conda-forge and the ROS vendor packages, and is the only collection
    the ROS repositories carry the gz packages themselves for, so the two
    tables do not have the same columns. A column nobody could ever fill reads
    as a gap, which is exactly what the dashboard is meant to make legible.
    """
    fetched = set(sources_fetched)
    columns: list[tuple[str, str]] = []
    for source in available_sources():
        if source not in fetched:
            continue
        if collection is not None and not config.source_applies(source, collection):
            continue
        for channel in source_class(source).channels or ("",):
            columns.append((source, channel))
    # Anything fetched but no longer registered still deserves a column.
    for source in sources_fetched:
        if source not in set(available_sources()):
            if collection is None or config.source_applies(source, collection):
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


STATUS_CSS: dict[Status, str] = {
    Status.UP_TO_DATE: "ok",
    Status.BEHIND: "behind",
    Status.MISSING: "missing",
    Status.AHEAD: "ahead",
    Status.NOT_EXPECTED: "none",
}


@dataclass
class Problem:
    """One finding, with every platform it affects collapsed into one line."""

    collection: str
    library: str
    major: int
    source: str
    channel: str
    status: Status
    found: str | None
    expected: str | None
    places: list[str]

    @property
    def title(self) -> str:
        return f"{self.collection}/{self.library}{self.major}"

    @property
    def glyph(self) -> str:
        return STATUS_GLYPHS[self.status]

    def where(self, limit: int | None = None) -> str:
        """The affected platforms, optionally trimmed to keep a line readable."""
        if limit is None or len(self.places) <= limit:
            return ", ".join(self.places)
        rest = len(self.places) - limit
        return ", ".join(self.places[:limit]) + f", +{rest} more"


def group_problems(entries: list[StatusEntry]) -> list[Problem]:
    """Collapse the problems that differ only by platform.

    conda-forge lagging on one library is one fact, not six; repeating it per
    subdirectory buries the findings that affect a single platform.
    """
    grouped: dict[tuple, Problem] = {}
    for entry in problems(entries):
        key = (
            entry.collection, entry.library, entry.major, entry.source,
            entry.channel, entry.status, entry.found_version, entry.expected_version,
        )
        place = f"{entry.platform}/{entry.arch}" if entry.arch else entry.platform
        if key in grouped:
            grouped[key].places.append(place)
        else:
            grouped[key] = Problem(*key, places=[place])
    return sorted(
        grouped.values(),
        key=lambda p: (-SEVERITY[p.status], p.collection, p.library, p.major, p.source),
    )

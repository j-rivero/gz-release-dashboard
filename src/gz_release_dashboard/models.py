"""Domain model shared by the fetchers, the status engine and the renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Status(StrEnum):
    """How a package in one source compares against the released tag."""

    UP_TO_DATE = "up_to_date"
    BEHIND = "behind"
    MISSING = "missing"
    AHEAD = "ahead"
    PRERELEASE = "prerelease"
    NOT_EXPECTED = "not_expected"


@dataclass(frozen=True, order=True)
class Library:
    """A Gazebo library at one major version, e.g. ``gz-sim`` 9."""

    name: str
    major: int

    def __str__(self) -> str:
        return f"{self.name} ({self.major})"


@dataclass
class Collection:
    """A Gazebo collection (jetty, ionic, ...) and the libraries it ships."""

    name: str
    in_development: bool
    libraries: list[Library] = field(default_factory=list)


@dataclass
class GroundTruthEntry:
    """Latest tags pushed to GitHub for one ``(library, major)``."""

    library: str
    major: int
    latest_stable: str | None = None
    latest_prerelease: str | None = None


@dataclass
class PackageRecord:
    """One version of one library observed in one source.

    ``platform`` is an opaque, source-defined display string: a Debian distro
    (``noble``), a conda subdir (``linux-64``), a brew bottle label
    (``arm64_sonoma``) or a ROS distro pinned to a distro (``jazzy@noble``).
    """

    source: str
    channel: str
    platform: str
    arch: str
    library: str
    major: int
    pkg_name: str
    raw_version: str
    upstream_version: str


@dataclass
class FetchError:
    """A non-fatal failure while fetching one source."""

    source: str
    message: str


@dataclass
class StatusEntry:
    """A single dashboard cell: recomputed at render time, never persisted."""

    collection: str
    library: str
    major: int
    source: str
    channel: str
    platform: str
    arch: str
    status: Status
    found_version: str | None = None
    expected_version: str | None = None


@dataclass
class Snapshot:
    """Everything a fetch run collected; the only thing renderers read."""

    schema_version: int
    generated_at: str
    tool_version: str
    sources_fetched: list[str] = field(default_factory=list)
    collections: list[Collection] = field(default_factory=list)
    ground_truth: list[GroundTruthEntry] = field(default_factory=list)
    records: list[PackageRecord] = field(default_factory=list)
    errors: list[FetchError] = field(default_factory=list)

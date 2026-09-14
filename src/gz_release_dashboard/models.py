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
    """A Gazebo collection (jetty, ionic, ...) and the libraries it ships.

    ``distros`` is the Linux releases the collection declares a packaging
    config for. It is the set of distros still worth looking at, not a
    per-collection restriction: upstream under-declares it (jetty lists only
    noble yet ships on resolute too), so only the union across collections is
    trustworthy. See :func:`~gz_release_dashboard.collections_yaml.linux_distros`.
    """

    name: str
    in_development: bool
    libraries: list[Library] = field(default_factory=list)
    distros: list[str] = field(default_factory=list)


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
class DependencyRecord:
    """What one collection's build in one system declares for a dependency.

    A dependency has no release tag to be scored against, so this is inventory
    rather than a status: the name the build wrote down (``declared``) and the
    version that name resolves to on ``platform``. ``platform`` is opaque and
    system-defined, as for :class:`PackageRecord`: ``noble/arm64``, a bottle
    label, a conda subdir, ``all``, ``lyrical@resolute/amd64``.

    ``version`` is ``None`` when nothing gave one. ``label`` tells the two
    reasons apart: a provider that was found but states no version (a ROS
    vendor, ``vendor 0.10.5``) carries one, a declaration nothing resolves
    does not.

    ``channel`` is the repository channel, for a system read from more than
    one: deb's ``stable``, or ``prerelease`` for a version still queued there.
    It is empty for the others, and in snapshots written before it existed.
    """

    collection: str
    library: str
    major: int
    dependency: str
    system: str
    platform: str
    declared: str
    version: str | None
    origin: str
    label: str | None = None
    channel: str = ""


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
    dependencies: list[DependencyRecord] = field(default_factory=list)
    errors: list[FetchError] = field(default_factory=list)

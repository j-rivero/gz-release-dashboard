"""Compare a snapshot against the ground truth. Pure: no network, no I/O."""

from __future__ import annotations

from . import config
from .models import (
    Collection,
    GroundTruthEntry,
    PackageRecord,
    Snapshot,
    Status,
    StatusEntry,
)
from .versions import GzVersion, max_version

#: Worst first: used to collapse a row of platforms into one cell.
SEVERITY = {
    Status.MISSING: 5,
    Status.BEHIND: 4,
    Status.AHEAD: 3,
    Status.UP_TO_DATE: 1,
    Status.NOT_EXPECTED: 0,
}


def expected_version(entry: GroundTruthEntry | None, channel: str) -> str | None:
    """What ``channel`` ought to be shipping for this library."""
    if entry is None:
        return None
    if entry.latest_stable is None:
        # Nothing stable was ever tagged: an in-development major.
        return entry.latest_prerelease
    if channel in config.PRERELEASE_CHANNELS:
        return max_version([entry.latest_stable, entry.latest_prerelease])
    return entry.latest_stable


def compare(found: str | None, expected: str | None) -> Status:
    """Status of a package that is present in a source."""
    found_version = GzVersion.parse(found)
    expected_ver = GzVersion.parse(expected)
    if found_version is None:
        return Status.MISSING
    if expected_ver is None:
        # No tag to compare against; whatever is published leads.
        return Status.AHEAD
    if found_version > expected_ver:
        return Status.AHEAD
    if found_version < expected_ver:
        return Status.BEHIND
    # A prerelease that matches what the channel is meant to hold is simply up
    # to date; the version string already says it is a prerelease.
    return Status.UP_TO_DATE


def absence_status(
    source: str,
    library: str,
    major: int,
    collection: Collection,
    channel: str,
    arch: str,
    arch_support: set[tuple[str, int, str]],
) -> Status:
    """Status of a package a source did not publish.

    Absence is only a problem where publishing was the plan. Three things mean
    it was not: the source never ships that library, the collection has not been
    released, and -- the big one -- the library is not built for that
    architecture anywhere, which is how the 32-bit story really works (gz-sim,
    gz-gui, gz-rendering, gz-launch and gz-sensors are absent from every armhf
    and i386 build by policy, not by oversight).
    """
    if library in config.EXPECTED_ABSENT.get(source, frozenset()):
        return Status.NOT_EXPECTED
    if collection.in_development and channel not in config.PRERELEASE_CHANNELS:
        # An unreleased collection has nothing to ship on a stable channel.
        return Status.NOT_EXPECTED
    if channel in config.PRERELEASE_CHANNELS:
        # Staging channels hold whatever is pending right now; an empty one
        # means nothing is queued, which is the normal state of affairs.
        return Status.NOT_EXPECTED
    if (library, major, arch) not in arch_support:
        return Status.NOT_EXPECTED
    return Status.MISSING


def architectures_built(records: list[PackageRecord], source: str) -> set[tuple[str, int, str]]:
    """Every ``(library, major, arch)`` this source is known to build."""
    return {(r.library, r.major, r.arch) for r in records if r.source == source}


def _observed_combos(
    records: list[PackageRecord], source: str, libraries: set[tuple[str, int]]
) -> list[tuple[str, str, str]]:
    """The (channel, platform, arch) cells this source builds this collection in.

    Presence of a single library is not enough evidence: majors are shared
    between collections (gz-tools 2 belongs to harmonic, ionic and jetty alike),
    so one leaked package would otherwise drag a whole collection onto a distro
    it was never built for. A platform counts only once it carries a real share
    of the collection; the architectures then come from whatever the source
    publishes there.
    """
    libraries_by_platform: dict[tuple[str, str], set[tuple[str, int]]] = {}
    arches_by_platform: dict[tuple[str, str], set[str]] = {}
    for record in records:
        if record.source != source:
            continue
        if config.overlaid_channel(source, record.channel) is not None:
            # An overlay channel has no matrix to be absent from; it is
            # reported from the records it actually holds, in _overlay_entries.
            continue
        platform = (record.channel, record.platform)
        arches_by_platform.setdefault(platform, set()).add(record.arch)
        if (record.library, record.major) in libraries:
            libraries_by_platform.setdefault(platform, set()).add(
                (record.library, record.major)
            )
    needed = max(1, round(len(libraries) * config.COLLECTION_PLATFORM_SHARE))
    return sorted(
        (channel, platform, arch)
        for (channel, platform), found in libraries_by_platform.items()
        if len(found) >= needed
        for arch in arches_by_platform[(channel, platform)]
    )


def _overlay_entries(
    records: list[PackageRecord],
    source: str,
    collection: Collection,
    library_keys: set[tuple[str, int]],
) -> list[StatusEntry]:
    """Entries for the channels of ``source`` that overlay another channel.

    There is no expected matrix here, so no absence cells: an overlay channel is
    empty until someone stages a release, and empty is its normal state. What is
    left after the source has dropped everything stable overtook is by
    definition ahead of stable -- a release on its way out, which is exactly
    what the channel should be holding. So it is up to date, full stop; there is
    nothing for it to be behind.
    """
    return [
        StatusEntry(
            collection=collection.name,
            library=record.library,
            major=record.major,
            source=source,
            channel=record.channel,
            platform=record.platform,
            arch=record.arch,
            status=Status.UP_TO_DATE,
            found_version=record.upstream_version,
            expected_version=None,
        )
        for record in records
        if record.source == source
        and config.overlaid_channel(source, record.channel) is not None
        and (record.library, record.major) in library_keys
    ]


def compute_statuses(snapshot: Snapshot) -> list[StatusEntry]:
    """One entry per (collection, library, source, channel, platform, arch)."""
    ground_truth = {(g.library, g.major): g for g in snapshot.ground_truth}
    by_key = {
        (r.source, r.channel, r.platform, r.arch, r.library, r.major): r
        for r in snapshot.records
    }
    entries: list[StatusEntry] = []
    for collection in snapshot.collections:
        library_keys = {(lib.name, lib.major) for lib in collection.libraries}
        for source in snapshot.sources_fetched:
            combos = _observed_combos(snapshot.records, source, library_keys)
            arch_support = architectures_built(snapshot.records, source)
            for library in collection.libraries:
                truth = ground_truth.get((library.name, library.major))
                for channel, platform, arch in combos:
                    expected = expected_version(truth, channel)
                    record = by_key.get(
                        (source, channel, platform, arch, library.name, library.major)
                    )
                    if record is not None:
                        status = compare(record.upstream_version, expected)
                        found = record.upstream_version
                    else:
                        status = absence_status(
                            source,
                            library.name,
                            library.major,
                            collection,
                            channel,
                            arch,
                            arch_support,
                        )
                        found = None
                    entries.append(
                        StatusEntry(
                            collection=collection.name,
                            library=library.name,
                            major=library.major,
                            source=source,
                            channel=channel,
                            platform=platform,
                            arch=arch,
                            status=status,
                            found_version=found,
                            expected_version=expected,
                        )
                    )
            entries.extend(
                _overlay_entries(snapshot.records, source, collection, library_keys)
            )
    return entries


def problems(entries: list[StatusEntry]) -> list[StatusEntry]:
    """The entries worth acting on.

    AHEAD is reported but never a problem, and neither is anything on a staging
    channel: those repositories hold whatever happens to be queued, so a leftover
    release candidate older than the shipped version is stale, not broken. The
    tables still show both; only this list drives the exit code.
    """
    return [
        e
        for e in entries
        if e.status in (Status.BEHIND, Status.MISSING)
        and e.channel not in config.PRERELEASE_CHANNELS
    ]

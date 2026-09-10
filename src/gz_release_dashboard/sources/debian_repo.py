"""Shared plumbing for the APT repositories we read.

packages.osrfoundation.org, repos.ros.org and packages.ros.org all publish
plain RFC822 ``Packages.gz`` indexes, so the stanza parser, the gz naming rules
and the walk over channels, distributions and architectures live here rather
than being written once per repository.
"""

from __future__ import annotations

import re
from typing import Iterator

from ..collections_yaml import linux_distros
from ..models import Collection, PackageRecord
from ..versions import GzVersion, normalize_deb
from .base import PackageSource

#: `gz-fuel-tools10` -> (gz-fuel-tools, 10). The major group is optional
#: because the first ignition release of a lib carried no suffix at all
#: (`ignition-tools`, `ignition-plugin`), which means major 1.
SOURCE_NAME_RE = re.compile(r"^(?P<base>[a-z][a-z-]*?)(?P<major>\d+)?$")


def parse_stanzas(text: str) -> Iterator[dict[str, str]]:
    """Yield each blank-line-separated RFC822 stanza as a dict."""
    stanza: dict[str, str] = {}
    key: str | None = None
    for line in text.splitlines():
        if not line.strip():
            if stanza:
                yield stanza
            stanza, key = {}, None
            continue
        if line[0] in " \t":  # a folded continuation of the previous field
            if key:
                stanza[key] += "\n" + line.strip()
            continue
        name, separator, value = line.partition(":")
        if not separator:
            continue
        key = name.strip()
        stanza[key] = value.strip()
    if stanza:
        yield stanza


def source_name(stanza: dict[str, str]) -> str:
    """The source package a binary came from; ``Source`` defaults to ``Package``."""
    source = stanza.get("Source") or stanza.get("Package", "")
    return source.split(" ", 1)[0]  # `Source: gz-sim10 (10.5.0-1)`


def canonical_library(base: str) -> str:
    """Rename the ignition era onto today's library names."""
    if base == "ignition-gazebo":
        return "gz-sim"
    if base.startswith("ignition-"):
        return "gz-" + base.removeprefix("ignition-")
    return base


def split_source_name(source: str) -> tuple[str, int] | None:
    """``ignition-gazebo6`` -> ``("gz-sim", 6)``; ``dart6.13`` -> ``None``."""
    match = SOURCE_NAME_RE.match(source)
    if not match:
        return None
    major = match.group("major")
    return canonical_library(match.group("base")), int(major) if major else 1


def packages_url(root: str, distro: str, arch: str) -> str:
    """The binary index of one distribution and architecture under ``root``."""
    return f"{root}/dists/{distro}/main/binary-{arch}/Packages.gz"


class AptSource(PackageSource):
    """A source that reads Debian binary indexes.

    Everything above the stanza is the same wherever the repository lives:
    walk the channels, the distributions and the architectures, fetch each
    index and split it. Subclasses say where the repositories are and what a
    stanza means to them.
    """

    #: channel -> the repository root the ``dists/`` tree hangs off. Every
    #: subclass declares its own; there is no sensible default.
    repositories: dict[str, str]
    #: The architectures to query, which is never every architecture indexed.
    arches: tuple[str, ...] = ()
    #: Used only if the collections declare no Linux packaging config at all.
    fallback_distros: tuple[str, ...] = ()

    def distros(self, collections: list[Collection]) -> tuple[str, ...]:
        """The Linux releases to ask for: the union across live collections.

        Never the per-collection list, which upstream under-declares (jetty
        names only noble yet ships on resolute too).
        """
        return linux_distros(collections) or self.fallback_distros

    def stanzas(
        self, collections: list[Collection]
    ) -> Iterator[tuple[str, str, str, dict[str, str]]]:
        """Yield ``(channel, distro, arch, stanza)`` for every index that exists.

        A missing index is not an error: no repository carries every
        distribution, and the combinations that do not exist simply say so
        with a 404.
        """
        for channel in self.channels:
            root = self.repositories[channel]
            for distro in self.distros(collections):
                for arch in self.arches:
                    text = self.http.get_gzip_text(
                        packages_url(root, distro, arch), ok_404=True
                    )
                    if not text:
                        continue
                    for stanza in parse_stanzas(text):
                        yield channel, distro, arch, stanza


class GzAptSource(AptSource):
    """An APT repository publishing the gz libraries under their own names.

    packages.osrfoundation.org is where they are built, and the ROS
    repositories mirror the very same source packages (``ignition-gazebo6``,
    ``sdformat12``, ...), so reading them is one job and not three. A
    subclass only declares its repositories; anything peculiar to one of them
    belongs in :meth:`finalize`.

    One record per (channel, distro, arch, library): the oldest version among
    the source package's binaries. A source package builds all of its binaries
    from one upload, so wherever a release landed whole they carry the same
    version. Where they disagree the release landed in pieces, and the oldest
    piece is what that architecture actually offers.
    """

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        known = {(lib.name, lib.major) for c in collections for lib in c.libraries}
        binaries: dict[tuple, PackageRecord] = {}
        for channel, distro, arch, stanza in self.stanzas(collections):
            record = self.record(stanza, channel, distro, arch)
            # The master filter: anything that is not a library of a live
            # collection is noise (dart, ogre, the gz-jetty metapackage, EOL
            # majors, and every ROS package in the ROS repositories).
            if record is None or (record.library, record.major) not in known:
                continue
            self._keep_newest(binaries, stanza.get("Package", ""), record)
        return self.finalize(list(self._lowest_per_library(binaries).values()))

    def finalize(self, records: list[PackageRecord]) -> list[PackageRecord]:
        """Last word on the records, for a repository with a rule of its own."""
        return records

    def record(
        self, stanza: dict[str, str], channel: str, distro: str, arch: str
    ) -> PackageRecord | None:
        package = stanza.get("Package", "")
        if package.endswith(("-dbg", "-dbgsym")):
            return None
        # `gz-jetty-cmake` and friends are alias packages pointing at the real
        # ones; they carry the same Source and version but a useless name.
        if stanza.get("Section") == "metapackages":
            return None
        source = source_name(stanza)
        split = split_source_name(source)
        if split is None:
            return None
        library, major = split
        raw_version = stanza.get("Version", "")
        upstream = normalize_deb(raw_version)
        if upstream is None:
            return None
        return PackageRecord(
            source=self.name,
            channel=channel,
            platform=distro,
            arch=arch,
            library=library,
            major=major,
            pkg_name=source,
            raw_version=raw_version,
            upstream_version=upstream,
        )

    @staticmethod
    def _keep_newest(
        binaries: dict[tuple, PackageRecord], package: str, record: PackageRecord
    ) -> None:
        """The newest stanza of one binary package: the version apt would install.

        An index may still carry an earlier stanza of a package it has since
        republished. That is history within one binary, not a source that
        landed in pieces, so it is resolved here and never reaches the
        comparison between binaries.
        """
        key = (
            record.channel,
            record.platform,
            record.arch,
            record.library,
            record.major,
            package,
        )
        previous = binaries.get(key)
        if previous is None or GzVersion.parse(record.upstream_version) > GzVersion.parse(
            previous.upstream_version
        ):
            binaries[key] = record

    @staticmethod
    def _lowest_per_library(
        binaries: dict[tuple, PackageRecord],
    ) -> dict[tuple, PackageRecord]:
        """Collapse a source's binaries into the oldest version among them.

        ``Architecture: all`` binaries are why this matters, and they are
        deliberately kept rather than skipped. A repository replicates them
        into every per-architecture index, so the doc and transitional packages
        an amd64 builder produced sit in binary-arm64 at the current version
        beside arm64 libraries that were never rebuilt. Ranking by the newest
        stanza lets that amd64 build speak for the architecture it was copied
        into: sdformat 15 arm64 stood three releases behind for seven months
        while the cell read 15.4.0. Taking the oldest instead means a cell is
        green only when every binary of the source really arrived.
        """
        best: dict[tuple, PackageRecord] = {}
        for key, record in binaries.items():
            library = key[:5]
            previous = best.get(library)
            if previous is None or GzVersion.parse(record.upstream_version) < GzVersion.parse(
                previous.upstream_version
            ):
                best[library] = record
        return best

"""packages.osrfoundation.org: the stable and prerelease Debian repositories."""

from __future__ import annotations

from .. import config
from ..collections_yaml import linux_distros
from ..models import Collection, PackageRecord
from ..versions import GzVersion, normalize_deb
from . import register_source
from .base import PackageSource
from .debian_repo import packages_url, parse_stanzas, source_name, split_source_name


@register_source
class OsrfDebianSource(PackageSource):
    """One record per (channel, distro, arch, library): the oldest version there.

    A source package builds all of its binaries from one upload, so wherever a
    release landed whole they carry the same version. Where they disagree the
    release landed in pieces, and the oldest piece is what that architecture
    actually offers.
    """

    name = "osrf_debian"
    channels = ("stable", "prerelease")

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        known = {(lib.name, lib.major) for c in collections for lib in c.libraries}
        # The union across collections, never per collection: upstream
        # under-declares (jetty lists only noble but ships on resolute too).
        distros = linux_distros(collections) or config.OSRF_DEB_DISTROS
        binaries: dict[tuple, PackageRecord] = {}
        for channel in self.channels:
            repository = config.OSRF_DEB_CHANNELS[channel]
            for distro in distros:
                for arch in config.deb_arches(distro):
                    url = packages_url(config.OSRF_DEB_BASE, repository, distro, arch)
                    text = self.http.get_gzip_text(url, ok_404=True)
                    if not text:
                        continue
                    for stanza in parse_stanzas(text):
                        record = self._record(stanza, channel, distro, arch)
                        # The master filter: anything that is not a library of a
                        # live collection is noise (dart, ogre, the gz-jetty
                        # metapackage, EOL majors).
                        if record is None or (record.library, record.major) not in known:
                            continue
                        self._keep_newest(binaries, stanza.get("Package", ""), record)
        return self._live_records(self._lowest_per_library(binaries))

    def _record(
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
    def _live_records(best: dict[tuple, PackageRecord]) -> list[PackageRecord]:
        """Drop prerelease entries that stable has already overtaken.

        Both repositories are enabled together, so apt installs whichever
        version is higher. A prerelease only means something while it is ahead
        of stable; at or below it, it is the release candidate of a release that
        already shipped, and reporting it would be reporting on history. Only
        one strictly ahead is a pending release worth showing.

        The comparison is against the highest stable version of that major
        anywhere in the repository, not the one sitting in the same distro and
        architecture. Once a major has been released, every older candidate for
        it is history regardless of where it lingers -- and lingering on the one
        architecture stable never built for is precisely how these survive
        (harmonic still has gz-msgs10 10.0.0-pre3 on jammy/i386, three minors
        after 10.4.0 shipped). A major with no stable release at all is the
        in-development case, and its candidates stand: that is what the
        repository is for.
        """
        shipped: dict[tuple[str, str, int], GzVersion] = {}
        for record in best.values():
            version = GzVersion.parse(record.upstream_version)
            key = (record.channel, record.library, record.major)
            if version is not None and (
                key not in shipped or version > shipped[key]
            ):
                shipped[key] = version
        records: list[PackageRecord] = []
        for record in best.values():
            base = config.overlaid_channel(record.source, record.channel)
            if base is not None:
                released = shipped.get((base, record.library, record.major))
                staged = GzVersion.parse(record.upstream_version)
                if released is not None and staged is not None and staged <= released:
                    continue
            records.append(record)
        return records

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

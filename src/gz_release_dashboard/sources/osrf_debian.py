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
    """One record per (channel, distro, arch, library): the newest version there."""

    name = "osrf_debian"
    channels = ("stable", "prerelease")

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        known = {(lib.name, lib.major) for c in collections for lib in c.libraries}
        # The union across collections, never per collection: upstream
        # under-declares (jetty lists only noble but ships on resolute too).
        distros = linux_distros(collections) or config.OSRF_DEB_DISTROS
        best: dict[tuple, PackageRecord] = {}
        for channel in self.channels:
            repository = config.OSRF_DEB_CHANNELS[channel]
            for distro in distros:
                for arch in config.OSRF_DEB_ARCHES:
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
                        self._keep_newest(best, record)
        return list(best.values())

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
    def _keep_newest(best: dict[tuple, PackageRecord], record: PackageRecord) -> None:
        key = (record.channel, record.platform, record.arch, record.library, record.major)
        previous = best.get(key)
        if previous is None or GzVersion.parse(record.upstream_version) > GzVersion.parse(
            previous.upstream_version
        ):
            best[key] = record

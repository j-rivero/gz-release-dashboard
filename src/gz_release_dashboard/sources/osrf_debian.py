"""packages.osrfoundation.org: the stable and prerelease Debian repositories."""

from __future__ import annotations

from .. import config
from ..models import PackageRecord
from ..versions import GzVersion
from . import register_source
from .debian_repo import GzAptSource


@register_source
class OsrfDebianSource(GzAptSource):
    """Where the gz packages are built, and the reference every mirror is read against.

    Nothing but the repositories is declared here: reading them is
    :class:`~gz_release_dashboard.sources.debian_repo.GzAptSource`'s job, shared
    with the ROS repositories that carry the same source packages. What is
    peculiar to this one is the prerelease overlay, which is what
    :meth:`finalize` is for.
    """

    name = "osrf_debian"
    channels = ("stable", "prerelease")
    repositories = config.OSRF_DEB_CHANNELS
    arches = config.OSRF_DEB_ARCHES
    fallback_distros = config.OSRF_DEB_DISTROS

    def finalize(self, records: list[PackageRecord]) -> list[PackageRecord]:
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
        for record in records:
            version = GzVersion.parse(record.upstream_version)
            key = (record.channel, record.library, record.major)
            if version is not None and (
                key not in shipped or version > shipped[key]
            ):
                shipped[key] = version
        live: list[PackageRecord] = []
        for record in records:
            base = config.overlaid_channel(record.source, record.channel)
            if base is not None:
                released = shipped.get((base, record.library, record.major))
                staged = GzVersion.parse(record.upstream_version)
                if released is not None and staged is not None and staged <= released:
                    continue
            live.append(record)
        return live

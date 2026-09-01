"""ROS 2 vendor packages on packages.ros.org.

A vendor package's own ``Version`` is the vendor recipe's version, not Gazebo's;
the upstream version it wraps is only ever stated in its ``Description``.
"""

from __future__ import annotations

import re

from .. import config
from ..models import Collection, PackageRecord
from ..versions import GzVersion
from . import register_source
from .base import PackageSource
from .debian_repo import canonical_library, packages_url, parse_stanzas

VENDOR_PACKAGE_RE = re.compile(r"^ros-(?P<rosdistro>[a-z]+)-[a-z0-9-]+-vendor$")
#: The colon matters: it separates the gz grammar ("Vendor package for: gz-sim8
#: 8.11.0 ...") from every other vendor's prose ("Vendor package for the DART
#: physics engine v6.13.2"), which carries no parseable upstream version.
DESCRIPTION_RE = re.compile(
    r"Vendor package for:\s+"
    r"(?P<pkg>[a-z][a-z0-9_-]*?)(?P<major>\d+)?\s+"
    r"(?P<version>\d+\.\d+\.\d+(?:-pre\d+)?)"
)


def parse_description(description: str) -> tuple[str, int, str] | None:
    """``Vendor package for: gz-fuel_tools9 9.1.1 ...`` -> (gz-fuel-tools, 9, 9.1.1)."""
    match = DESCRIPTION_RE.search(description or "")
    if not match:
        return None
    library = canonical_library(match.group("pkg").replace("_", "-"))
    major = int(match.group("major") or 1)
    version = GzVersion.parse(match.group("version"))
    if version is None or version.major != major:
        return None
    return library, major, str(version)


@register_source
class RosVendorSource(PackageSource):
    """One record per (channel, rosdistro@distro, arch, library)."""

    name = "ros_vendor"
    channels = ("ros2", "ros2-testing")

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        known = {(lib.name, lib.major) for c in collections for lib in c.libraries}
        best: dict[tuple, PackageRecord] = {}
        for channel in self.channels:
            repository = config.ROS_DEB_CHANNELS[channel]
            for distro in config.ROS_DEB_DISTROS:
                for arch in config.ROS_DEB_ARCHES:
                    url = packages_url(
                        config.ROS_DEB_BASE, f"{repository}/ubuntu", distro, arch
                    )
                    text = self.http.get_gzip_text(url, ok_404=True)
                    if not text:
                        continue
                    for stanza in parse_stanzas(text):
                        record = self._record(stanza, channel, distro, arch)
                        # No rosdistro-to-collection table: a vendor package
                        # belongs wherever its (library, major) is shipped.
                        if record is None or (record.library, record.major) not in known:
                            continue
                        key = (
                            record.channel, record.platform, record.arch,
                            record.library, record.major,
                        )
                        previous = best.get(key)
                        if previous is None or GzVersion.parse(
                            record.upstream_version
                        ) > GzVersion.parse(previous.upstream_version):
                            best[key] = record
        return list(best.values())

    def _record(
        self, stanza: dict[str, str], channel: str, distro: str, arch: str
    ) -> PackageRecord | None:
        package = stanza.get("Package", "")
        if package.endswith("-dbgsym"):
            return None
        match = VENDOR_PACKAGE_RE.match(package)
        if not match:
            return None
        parsed = parse_description(stanza.get("Description", ""))
        if parsed is None:
            return None
        library, major, upstream = parsed
        return PackageRecord(
            source=self.name,
            channel=channel,
            platform=f"{match.group('rosdistro')}@{distro}",
            arch=arch,
            library=library,
            major=major,
            pkg_name=package,
            raw_version=stanza.get("Version", ""),
            upstream_version=upstream,
        )

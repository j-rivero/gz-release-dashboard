"""What the ROS 2 vendor packages of a collection depend on, and what that gets.

ROS users install Gazebo as vendor packages from packages.ros.org, so their
dependencies are whatever those vendor packages' ``Depends`` name, resolved
where a ROS system resolves them. That is one of two places. A dependency
vendored for ROS (``gz-dartsim-vendor``) is a stanza in the same index, and like
every vendor it states its upstream version only in prose. Everything else
(``libbullet-dev``) comes from Ubuntu, never from packages.osrfoundation.org,
which a ROS system does not enable.

No table says which collection a rosdistro serves. It follows from what the
rosdistro carries, by the same share rule the status engine uses to hand Rolling
to a single collection.
"""

from __future__ import annotations

import re
from typing import Iterable, Iterator

from .. import config
from ..collections_yaml import linux_distros
from ..engine import carries_collection
from ..models import Collection, DependencyRecord, FetchError, Library
from ..sources.debian_repo import packages_url, parse_stanzas
from ..sources.ros_vendor import VENDOR_PACKAGE_RE, parse_description
from ..versions import dependency_version
from . import register_reader
from .aliases import match_dependency, unmapped_error
from .base import DependencyReader
from .relations import parse_relations
from .ubuntu import UbuntuResolver

#: How a dependency vendor states what it wraps, when it does at all:
#: ``the DART physics engine v6.16.6``, ``MuJoCo simulator of version 3.4.0``.
UPSTREAM_VERSION_RE = re.compile(r"(?:\bv|\bversion\s+)(\d+(?:\.\d+)+)")
#: What a dependency gets is read from stable alone: ros2-testing holds
#: whatever is waiting for the next sync.
CHANNEL = "ros2"
#: Read only to settle who owns a rosdistro, as the status engine settles it.
STAGING_CHANNEL = "ros2-testing"
#: Gazebo names the dependencies it vendors for ROS ``gz-<name>-vendor``
#: (gz-dartsim-vendor, gz-ogre-next-vendor). Any other vendor a gz vendor
#: depends on (spdlog-vendor) is ROS's own, and no gap in the alias table.
GZ_VENDOR_PREFIX = "gz-"


def upstream_version(description: str) -> str | None:
    """``Vendor package for Ogre-next v2.3.3`` -> ``2.3.3``; ``None`` if unstated."""
    match = UPSTREAM_VERSION_RE.search(description)
    return match.group(1) if match else None


class VendorIndex:
    """The vendor packages of one ros2 index: one distribution, one architecture."""

    def __init__(self, text: str) -> None:
        #: Every ``ros-<rosdistro>-*-vendor`` stanza, by package name.
        self.vendors: dict[str, dict[str, str]] = {}
        #: The gz vendors among them, by ``(rosdistro, library, major)``.
        self.gz: dict[tuple[str, str, int], dict[str, str]] = {}
        for stanza in parse_stanzas(text):
            package = stanza.get("Package", "")
            match = VENDOR_PACKAGE_RE.match(package)
            if not match:
                continue
            self.vendors[package] = stanza
            parsed = parse_description(stanza.get("Description", ""))
            if parsed is not None:
                library, major, _ = parsed
                self.gz[(match.group("rosdistro"), library, major)] = stanza

    def is_other_vendor(self, package: str) -> bool:
        """A vendor this index holds that does not wrap a gz library."""
        stanza = self.vendors.get(package)
        return stanza is not None and parse_description(stanza.get("Description", "")) is None


def served_rosdistros(
    indexes: Iterable[VendorIndex], collections: list[Collection]
) -> dict[str, list[str]]:
    """``{collection: [rosdistro, ...]}``: which rosdistros serve each collection.

    A pinned rosdistro serves every collection it carries a real share of, and
    since majors are shared that can be more than one. Rolling keeps the
    previous generation's vendors long after moving on, so it serves only the
    newest collection it carries, exactly as it is scored in the status engine.
    """
    carried: dict[str, set[tuple[str, int]]] = {}
    for index in indexes:
        for rosdistro, library, major in index.gz:
            carried.setdefault(rosdistro, set()).add((library, major))
    served: dict[str, list[str]] = {}
    for rosdistro, libraries in carried.items():
        owners = [c.name for c in collections if carries_collection(libraries, c)]
        if rosdistro in config.ROLLING_ROSDISTROS:
            owners = owners[-1:]  # collections arrive oldest first
        for owner in owners:
            served.setdefault(owner, []).append(rosdistro)
    return served


def vendor_resolution(stanza: dict[str, str] | None) -> tuple[str | None, str, str | None]:
    """``(version, origin, label)`` from a dependency vendor's own stanza.

    zenoh-cpp-vendor names no upstream version, but it was found, and its own
    recipe version is still worth showing in place of a bare ``?``.
    """
    if stanza is None:
        return None, "", None
    version = upstream_version(stanza.get("Description", ""))
    if version is not None:
        return version, CHANNEL, None
    return None, CHANNEL, f"vendor {dependency_version(stanza.get('Version'))}"


@register_reader
class RosVendorDepsReader(DependencyReader):
    """One record per tracked declaration, per ``rosdistro@distro/arch``.

    Reads the same ros2 and ros2-testing indexes as the ``ros_vendor`` source,
    so a run that fetched that source downloads nothing new but the one madison
    request.
    """

    system = "ros"

    def read(self, collections: list[Collection]) -> list[DependencyRecord]:
        self.errors = []
        indexes = self._indexes(collections, CHANNEL)
        # Ownership counts the staged vendors too, because the status engine
        # does: m owns Rolling once its vendors reach ros2-testing, even while
        # ros2 still holds jetty's, and jetty must not get those back here.
        staged = self._indexes(collections, STAGING_CHANNEL)
        served = served_rosdistros([*indexes.values(), *staged.values()], collections)
        records: list[DependencyRecord] = []
        # Plain Debian names wait for a single madison request covering them all.
        on_ubuntu: list[tuple[DependencyRecord, str, str]] = []
        for (distro, arch), index in indexes.items():
            for collection in self.applicable(collections):
                for rosdistro in served.get(collection.name, []):
                    platform = f"{rosdistro}@{distro}/{arch}"
                    for library in collection.libraries:
                        vendor = index.gz.get((rosdistro, library.name, library.major))
                        if vendor is None:
                            continue
                        for record, plain in self._declarations(
                            vendor, index, collection, library, rosdistro, platform
                        ):
                            records.append(record)
                            if plain:
                                on_ubuntu.append((record, distro, arch))
        self._resolve_on_ubuntu(on_ubuntu)
        return records

    def _indexes(
        self, collections: list[Collection], channel: str
    ) -> dict[tuple[str, str], VendorIndex]:
        """The indexes of ``channel`` that exist, by ``(distro, arch)``.

        The distributions and architectures are those ``ros_vendor`` walks, so
        these are the very URLs the run's memo already holds.
        """
        root = config.ROS_VENDOR_CHANNELS[channel]
        indexes: dict[tuple[str, str], VendorIndex] = {}
        for distro in linux_distros(collections) or config.ROS_DEB_DISTROS:
            for arch in config.ROS_DEB_ARCHES:
                text = self.http.get_gzip_text(packages_url(root, distro, arch), ok_404=True)
                if text:
                    indexes[(distro, arch)] = VendorIndex(text)
        return indexes

    def _declarations(
        self,
        vendor: dict[str, str],
        index: VendorIndex,
        collection: Collection,
        library: Library,
        rosdistro: str,
        platform: str,
    ) -> Iterator[tuple[DependencyRecord, bool]]:
        """The tracked dependencies one gz vendor declares, each with whether it
        is a plain Debian name that Ubuntu still has to resolve."""
        prefix = f"ros-{rosdistro}-"
        for relation in parse_relations(vendor.get("Depends", "")):
            for alternative in relation:
                name = alternative.name
                plain = not name.startswith(prefix)
                if plain:
                    declared = name
                    dependency = match_dependency("deb", name)
                    version, origin, label = None, "", None
                else:
                    declared = name.removeprefix(prefix)
                    dependency = match_dependency("ros", declared)
                    version, origin, label = vendor_resolution(index.vendors.get(name))
                if dependency is None:
                    if (
                        not plain
                        and declared.startswith(GZ_VENDOR_PREFIX)
                        and index.is_other_vendor(name)
                    ):
                        self._report(
                            unmapped_error(
                                collection.name, library.name, library.major, name, where=CHANNEL
                            )
                        )
                    continue
                record = DependencyRecord(
                    collection=collection.name,
                    library=library.name,
                    major=library.major,
                    dependency=dependency,
                    system=self.system,
                    platform=platform,
                    declared=declared,
                    version=version,
                    origin=origin,
                    label=label,
                )
                yield record, plain
                break  # the first tracked alternative speaks for the relation

    def _resolve_on_ubuntu(self, pending: list[tuple[DependencyRecord, str, str]]) -> None:
        """Fill in the plain Debian names from one madison request.

        If madison cannot be asked they stay unresolved and the reading says
        so: a ROS system gets them from Ubuntu alone, so no other repository's
        version would be the true answer.
        """
        names = [record.declared for record, _, _ in pending]
        distros = list(dict.fromkeys(distro for _, distro, _ in pending))
        arches = list(dict.fromkeys(arch for _, _, arch in pending))
        try:
            found = UbuntuResolver(self.http).resolve(names, distros, arches)
        except Exception as exc:  # noqa: BLE001 - the ROS versions still stand
            self.errors.append(
                FetchError(
                    "deps:ubuntu", f"Ubuntu not consulted for ROS vendor dependencies: {exc}"
                )
            )
            return
        for record, distro, arch in pending:
            raw = found.get((record.declared, distro, arch))
            if raw is not None:
                record.version = dependency_version(raw)
                record.origin = "ubuntu"

    def _report(self, error: FetchError) -> None:
        # The same unmapped name turns up once per distribution and architecture.
        if error not in self.errors:
            self.errors.append(error)

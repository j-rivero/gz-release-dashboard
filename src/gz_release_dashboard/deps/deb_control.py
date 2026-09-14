"""The deb system: what gazebo-release control files declare, and what that gets.

The osrf repository does not say which dart a gz build uses: it carries
libdart6.13-dev and libdart6.16-dev side by side, because on Debian the series
is part of the binary name. The build's own debian/control does say, by exact
name, so that is what is read -- one gazebo-release repository per
``(library, major)`` -- and every name is then looked up where a user's apt
looks: packages.osrfoundation.org and the Ubuntu archive beneath it.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, replace

import requests

from .. import config
from ..collections_yaml import linux_distros
from ..ground_truth import candidate_tag_prefixes
from ..models import Collection, DependencyRecord, FetchError, Library
from ..sources.debian_repo import packages_url, parse_stanzas, source_name, split_source_name
from ..versions import dependency_version, version_key
from . import register_reader
from .aliases import match_dependency, unmapped_error
from .base import DependencyReader
from .relations import Alternative, parse_relations
from .ubuntu import UbuntuResolver

#: How many links a ``<distro>/debian/control`` may go through. The convention
#: is one, ``../../ubuntu/debian/control``; anything longer is a mistake.
MAX_LINK_HOPS = 2

Relations = list[list[Alternative]]


def release_repos(library: Library) -> list[str]:
    """``gz-sim`` 6 -> gz-sim6-release, ignition-gazebo6-release, ign-gazebo6-release.

    The packaging repositories were named like the tags of their era, so the
    tag prefixes that carry a major are the candidates, in the same order.
    """
    return [
        prefix.removesuffix("_") + "-release"
        for prefix in candidate_tag_prefixes(library.name, library.major)
        if prefix.endswith(f"{library.major}_")
    ]


def is_link(body: str) -> bool:
    """A one-line body with no field in it is a relative path, not a control file."""
    lines = body.strip().splitlines()
    return len(lines) == 1 and ":" not in lines[0]


def build_depends(control: str) -> Relations:
    """The Build-Depends of a control file's source stanza.

    Comment lines go first. The stanza parser knows nothing of them, and one
    with a colon in it, inside Build-Depends, would open a field of its own
    and take every dependency listed after it along.
    """
    text = "\n".join(line for line in control.splitlines() if not line.startswith("#"))
    source = next(parse_stanzas(text), {})
    return parse_relations(source.get("Build-Depends", ""))


def tracked(relation: list[Alternative]) -> list[tuple[Alternative, str]]:
    """The alternatives that are tracked dependencies, each with the one it is."""
    pairs = []
    for alternative in relation:
        dependency = match_dependency("deb", alternative.name)
        if dependency is not None:
            pairs.append((alternative, dependency))
    return pairs


@dataclass
class ReleaseBuild:
    """What one gazebo-release repository declares."""

    #: distro -> Build-Depends, for every live distro with a control file.
    distros: dict[str, Relations]
    #: ubuntu/debian/control, for when no distro has a file of its own.
    default: Relations

    def declared(self, collection: Collection) -> dict[str, Relations]:
        """Build-Depends by distro.

        The distro files say where a library is built. ``collection.distros``
        cannot: it comes from the release jobs' packaging configs, which name
        the one distro a job builds on (jetty lists noble, osrf publishes it on
        resolute too), so it only stands in when no distro has a file.
        """
        if self.distros:
            return self.distros
        return {distro: self.default for distro in collection.distros}


@dataclass(frozen=True)
class OsrfBinary:
    version: str
    source: str


@dataclass
class OsrfIndex:
    """One osrf index, cut down to what resolution and the alias check use."""

    binaries: dict[str, OsrfBinary]
    #: Sources building at least one tracked binary: dart, ogre-next-2.3, ...
    tracked_sources: set[str]

    def unmapped(self, name: str, gz_libraries: set[str]) -> bool:
        """Hosted by Gazebo, not a gz library and in no alias: the table fell behind.

        A component of a source that is already tracked is not reported:
        libdart6.16-collision-bullet-dev beside libdart6.16-dev is a finer
        declaration of dart, not a dependency the table is missing, and
        gz-physics9 alone declares seven of them.
        """
        binary = self.binaries.get(name)
        if binary is None or match_dependency("deb", name) is not None:
            return False
        split = split_source_name(binary.source)
        if split is not None and split[0] in gz_libraries:
            return False
        return binary.source not in self.tracked_sources


@register_reader
class DebControlReader(DependencyReader):
    """Build-Depends of the gazebo-release repositories, resolved per distro and arch.

    apt enables the osrf repository on top of Ubuntu and installs the higher
    of the two, so both are asked: osrf through the same stable indexes
    ``osrf_debian`` reads, Ubuntu through one madison request per read. The
    osrf prerelease indexes are read too, for what is queued beyond that.
    """

    system = "deb"

    def read(self, collections: list[Collection]) -> list[DependencyRecord]:
        self.errors = []
        live = linux_distros(collections) or config.OSRF_DEB_DISTROS
        declared = self._declared(self.applicable(collections), live)
        names = {
            alternative.name
            for *_, relations in declared
            for relation in relations
            for alternative, _ in tracked(relation)
        }
        ubuntu = self._ubuntu(names, live)
        gz_libraries = {library.name for c in collections for library in c.libraries}
        indexes: dict[tuple[str, str], OsrfIndex] = {}
        prerelease: dict[tuple[str, str], OsrfIndex] = {}
        records: list[DependencyRecord] = []
        for collection, library, distro, relations in declared:
            for arch in config.OSRF_DEB_ARCHES:
                if (distro, arch) not in indexes:
                    indexes[distro, arch] = self._osrf_index(distro, arch, "stable")
                    prerelease[distro, arch] = self._osrf_index(distro, arch, "prerelease")
                osrf = indexes[distro, arch]
                self._check_aliases(collection, library, relations, arch, osrf, gz_libraries)
                for relation in relations:
                    alternatives = [pair for pair in tracked(relation) if pair[0].applies_to(arch)]
                    if not alternatives:
                        continue
                    record = self._record(
                        collection, library, distro, arch, alternatives, osrf, ubuntu
                    )
                    records.append(record)
                    queued = self._queued(record, alternatives, prerelease[distro, arch])
                    if queued is not None:
                        records.append(queued)
        return records

    def _declared(
        self, collections: list[Collection], live: tuple[str, ...]
    ) -> list[tuple[Collection, Library, str, Relations]]:
        """``(collection, library, distro, Build-Depends)`` for every build found.

        A major shared by several collections is read once and declared in each.
        """
        builds: dict[Library, ReleaseBuild | None] = {}
        declared = []
        for collection in collections:
            for library in collection.libraries:
                if library not in builds:
                    builds[library] = self._release_build(library, live)
                build = builds[library]
                if build is None:
                    continue
                for distro, relations in build.declared(collection).items():
                    declared.append((collection, library, distro, relations))
        return declared

    def _ubuntu(self, names: set[str], live: tuple[str, ...]) -> dict[tuple[str, str, str], str]:
        """Ubuntu's versions of ``names``, or none at all if madison cannot be reached.

        osrf is still worth reading on its own: a dependency Gazebo builds is
        exactly one Ubuntu does not carry, so most of what matters survives.
        """
        try:
            return UbuntuResolver(self.http).resolve(
                list(names), list(live), list(config.OSRF_DEB_ARCHES)
            )
        except requests.RequestException as exc:
            self.errors.append(
                FetchError(
                    "deps:ubuntu",
                    f"Ubuntu was not consulted, deb versions are osrf's alone: {exc}",
                )
            )
            return {}

    def _check_aliases(
        self,
        collection: Collection,
        library: Library,
        relations: Relations,
        arch: str,
        osrf: OsrfIndex,
        gz_libraries: set[str],
    ) -> None:
        for relation in relations:
            for alternative in relation:
                if not alternative.applies_to(arch):
                    continue
                if not osrf.unmapped(alternative.name, gz_libraries):
                    continue
                error = unmapped_error(
                    collection.name, library.name, library.major, alternative.name, where="osrf"
                )
                # One report per build, however many indexes host the name.
                if error not in self.errors:
                    self.errors.append(error)

    def _record(
        self,
        collection: Collection,
        library: Library,
        distro: str,
        arch: str,
        alternatives: list[tuple[Alternative, str]],
        osrf: OsrfIndex,
        ubuntu: dict[tuple[str, str, str], str],
    ) -> DependencyRecord:
        """The first alternative that resolves; the first of them all if none does."""
        chosen, dependency = alternatives[0]
        version: str | None = None
        origin = ""
        for alternative, candidate in alternatives:
            found = []
            if alternative.name in osrf.binaries:
                found.append((osrf.binaries[alternative.name].version, "osrf"))
            upstream = dependency_version(ubuntu.get((alternative.name, distro, arch)))
            if upstream is not None:
                found.append((upstream, "ubuntu"))
            if found:
                # apt installs the higher. max keeps the first of equals and osrf
                # is listed first, so a tie is reported as osrf.
                version, origin = max(found, key=lambda pair: version_key(pair[0]))
                chosen, dependency = alternative, candidate
                break
        return DependencyRecord(
            collection=collection.name,
            library=library.name,
            major=library.major,
            dependency=dependency,
            system=self.system,
            platform=f"{distro}/{arch}",
            declared=chosen.name,
            version=version,
            origin=origin,
            channel="stable",
        )

    @staticmethod
    def _queued(
        stable: DependencyRecord,
        alternatives: list[tuple[Alternative, str]],
        prerelease: OsrfIndex,
    ) -> DependencyRecord | None:
        """What osrf prerelease holds beyond ``stable`` on the same platform, if anything.

        The first alternative prerelease carries is the one apt would pick
        there. It is queued only while it is higher than what stable resolves:
        once stable has caught up, what is left in prerelease is history.
        """
        for alternative, dependency in alternatives:
            binary = prerelease.binaries.get(alternative.name)
            if binary is None:
                continue
            if stable.version is not None and (
                version_key(binary.version) <= version_key(stable.version)
            ):
                return None
            return replace(
                stable,
                dependency=dependency,
                declared=alternative.name,
                version=binary.version,
                origin="osrf",
                label=None,
                channel="prerelease",
            )
        return None

    def _release_build(self, library: Library, live: tuple[str, ...]) -> ReleaseBuild | None:
        """The first candidate repository that has an ubuntu/debian/control."""
        for repo in release_repos(library):
            default = self._control(repo, "ubuntu")
            if default is None:
                continue
            distros = {}
            for distro in live:
                control = self._control(repo, distro)
                # A distro with no file of its own is one this library is not built for.
                if control is not None:
                    distros[distro] = build_depends(control)
            return ReleaseBuild(distros, build_depends(default))
        return None

    def _control(self, repo: str, directory: str) -> str | None:
        """``<directory>/debian/control`` with its links followed; ``None`` if absent.

        A link that leads nowhere, or not to a control file within
        MAX_LINK_HOPS, is reported and read as declaring nothing. It still
        counts as a file, so ubuntu/debian/control does not quietly stand in.
        """
        path = f"{directory}/debian/control"
        body = self._get(repo, path)
        hops = 0
        while body is not None and is_link(body) and hops < MAX_LINK_HOPS:
            path = posixpath.normpath(posixpath.join(posixpath.dirname(path), body.strip()))
            body = self._get(repo, path)
            hops += 1
        if hops == 0 or (body is not None and not is_link(body)):
            return body
        self.errors.append(
            FetchError(
                "deps:deb",
                f"{repo}: {directory}/debian/control does not reach a control file "
                f"within {MAX_LINK_HOPS} links",
            )
        )
        return ""

    def _get(self, repo: str, path: str) -> str | None:
        return self.http.get_text(
            config.GAZEBO_RELEASE_URL.format(repo=repo, path=path), ok_404=True
        )

    def _osrf_index(self, distro: str, arch: str, channel: str) -> OsrfIndex:
        text = self.http.get_gzip_text(
            packages_url(config.OSRF_DEB_CHANNELS[channel], distro, arch), ok_404=True
        )
        binaries: dict[str, OsrfBinary] = {}
        for stanza in parse_stanzas(text or ""):
            version = dependency_version(stanza.get("Version"))
            if version is None:
                continue
            name = stanza.get("Package", "")
            previous = binaries.get(name)
            # An index may still hold an earlier stanza of a binary it has since
            # republished; apt installs the newest.
            if previous is None or version_key(version) > version_key(previous.version):
                binaries[name] = OsrfBinary(version, source_name(stanza))
        tracked_sources = {
            binary.source for name, binary in binaries.items() if match_dependency("deb", name)
        }
        return OsrfIndex(binaries, tracked_sources)

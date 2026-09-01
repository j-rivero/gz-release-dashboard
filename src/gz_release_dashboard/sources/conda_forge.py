"""conda-forge, read through the small per-package anaconda.org API.

Never channeldata.json: that is a single 22 MB document for the whole channel.
"""

from __future__ import annotations

from .. import config
from ..models import Collection, PackageRecord
from ..versions import GzVersion
from . import register_source
from .base import PackageSource


def subdir_arch(subdir: str) -> str:
    """``linux-aarch64`` -> ``aarch64``; conda spells plain 64-bit x86 as ``64``."""
    tail = subdir.rsplit("-", 1)[-1]
    return "x86_64" if tail == "64" else tail


@register_source
class CondaForgeSource(PackageSource):
    """One record per (library, major, subdir): the newest build published there."""

    name = "conda_forge"
    channels = ()

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        libraries = sorted({lib for c in collections for lib in c.libraries})
        cache: dict[str, dict | None] = {}
        records: list[PackageRecord] = []
        for library in libraries:
            best: dict[str, tuple[GzVersion, str]] = {}
            for name in self.candidate_names(library.name, library.major):
                data = self._package(name, cache)
                if not data:
                    continue
                for subdir, version in self._subdir_versions(data, library.major).items():
                    previous = best.get(subdir)
                    if previous is None or version > previous[0]:
                        best[subdir] = (version, name)
            for subdir, (version, name) in sorted(best.items()):
                records.append(
                    PackageRecord(
                        source=self.name,
                        channel="",
                        platform=subdir,
                        arch=subdir_arch(subdir),
                        library=library.name,
                        major=library.major,
                        pkg_name=name,
                        raw_version=str(version),
                        upstream_version=str(version),
                    )
                )
        return records

    @staticmethod
    def candidate_names(library: str, major: int) -> list[str]:
        """The live unversioned feedstock, then the frozen legacy one.

        conda-forge migrated gz to unversioned package names, but the old
        ``gz-sim9``-style feedstocks still exist and can hold a different
        version, so both are consulted and the newer one wins.
        """
        unversioned = config.CONDA_NAME_OVERRIDES.get(library, library)
        return [unversioned, f"{unversioned}{major}"]

    def _package(self, name: str, cache: dict[str, dict | None]) -> dict | None:
        if name not in cache:
            url = config.ANACONDA_PACKAGE_URL.format(name=name)
            cache[name] = self.http.get_json(url, ok_404=True)
        return cache[name]

    @staticmethod
    def _subdir_versions(data: dict, major: int) -> dict[str, GzVersion]:
        """Newest version of ``major`` per conda subdir.

        ``files`` is authoritative because it pairs every build with its subdir;
        ``platforms`` only reports each subdir's overall latest, which belongs to
        whichever major happens to be newest.
        """
        best: dict[str, GzVersion] = {}
        for entry in data.get("files") or []:
            subdir = (entry.get("attrs") or {}).get("subdir")
            version = GzVersion.parse(entry.get("version"))
            if not subdir or version is None or version.major != major:
                continue
            if subdir not in best or version > best[subdir]:
                best[subdir] = version
        if best:
            return best
        # No per-file detail: fall back to the flat version list.
        versions = [
            v
            for v in (GzVersion.parse(x) for x in data.get("versions") or [])
            if v is not None and v.major == major
        ]
        return {"all": max(versions)} if versions else {}

"""Bazel Central Registry: one metadata.json per (unversioned) module."""

from __future__ import annotations

from .. import config
from ..models import Collection, PackageRecord
from ..versions import GzVersion, normalize_bcr
from . import register_source
from .base import PackageSource


@register_source
class BazelRegistrySource(PackageSource):
    """A flat source: the registry is one global list, with no platform axis."""

    name = "bazel_registry"
    channels = ()

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        libraries = sorted({lib for c in collections for lib in c.libraries})
        # Module names carry no major version, so one fetch serves every major.
        modules = sorted({lib.name for lib in libraries})
        metadata = {name: self._metadata(name) for name in modules}
        records = []
        for library in libraries:
            data = metadata.get(library.name)
            if not data:
                continue
            record = self._record(library.name, library.major, data)
            if record:
                records.append(record)
        return records

    def _metadata(self, module: str) -> dict | None:
        # Always the CDN: the GitHub contents API truncates at 1000 entries and
        # silently drops modules (sdformat among them).
        url = config.BCR_METADATA_URL.format(module=module)
        return self.http.get_json(url, ok_404=True)

    def _record(self, library: str, major: int, data: dict) -> PackageRecord | None:
        yanked = set(data.get("yanked_versions") or {})
        best: GzVersion | None = None
        raw = ""
        for version in data.get("versions") or []:
            if version in yanked:
                continue
            # `.bcr.N` is a registry repack of an unchanged upstream release.
            upstream = GzVersion.parse(normalize_bcr(version))
            if upstream is None or upstream.major != major:
                continue
            # `versions` is append-ordered, so on a tie the later entry is the
            # registry's current spelling of that release (`4.0.0.bcr.1`).
            if best is None or upstream >= best:
                best, raw = upstream, version
        if best is None:
            return None
        return PackageRecord(
            source=self.name,
            channel="",
            platform="all",
            arch="all",
            library=library,
            major=major,
            pkg_name=library,
            raw_version=raw,
            upstream_version=str(best),
        )

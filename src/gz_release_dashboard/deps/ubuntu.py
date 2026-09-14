"""The Ubuntu archive, asked through madison rather than read index by index.

Most of what a gz build declares is not built by Gazebo at all: libbullet-dev
and libogre-1.9-dev come from Ubuntu, and the osrf repository only sits on top
of it. Reading universe the way the osrf indexes are read would cost a 19 MB
Packages.gz per distribution and architecture; madison answers every name,
suite and architecture we need in one request of a few kilobytes.
"""

from __future__ import annotations

from .. import config
from ..sources.base import Http
from ..versions import dependency_version, version_key


def madison_url(names: list[str], suites: list[str], arches: list[str]) -> str:
    return (
        f"{config.MADISON_URL}?package={'+'.join(names)}"
        f"&s={','.join(suites)}&a={','.join(arches)}&text=on"
    )


class UbuntuResolver:
    """Binary package versions in the Ubuntu archive, every pocket included."""

    def __init__(self, http: Http) -> None:
        self.http = http

    def resolve(
        self, names: list[str], distros: list[str], arches: list[str]
    ) -> dict[tuple[str, str, str], str]:
        """``{(name, distro, arch): raw version}`` for whatever Ubuntu has.

        A name Ubuntu does not carry is simply absent. A failure to reach
        madison is not caught here: the caller decides what a reading without
        Ubuntu is still worth.
        """
        wanted = sorted(set(names))
        if not wanted:
            return {}
        suites = [f"{distro}{pocket}" for distro in distros for pocket in config.UBUNTU_POCKETS]
        text = self.http.get_text(madison_url(wanted, suites, list(arches))) or ""
        return parse_madison(text, set(distros), set(arches))


def parse_madison(
    text: str, distros: set[str], arches: set[str]
) -> dict[tuple[str, str, str], str]:
    """Read ``name | version | suite/component | arch, arch`` lines.

    Every pocket counts as its distribution -- an update is what apt installs
    -- so the highest version across them is kept, whatever order madison
    lists them in.
    """
    best: dict[tuple[str, str, str], str] = {}
    for line in text.splitlines():
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 4:
            continue
        name, raw, suite, listed = fields
        distro = suite.split("/", 1)[0].split("-", 1)[0]
        upstream = dependency_version(raw)
        if distro not in distros or upstream is None:
            continue
        for arch in (a.strip() for a in listed.split(",")):
            if arch not in arches:
                continue
            key = (name, distro, arch)
            previous = best.get(key)
            if previous is None or version_key(upstream) > version_key(
                dependency_version(previous)
            ):
                best[key] = raw
    return best

"""Latest released version per library, read from the GitHub release tags.

``git ls-remote`` is used rather than the REST API: it needs no token, has no
rate limit and returns every tag in one request (``/tags`` paginates, and the
newest gz-sim majors land on page two).
"""

from __future__ import annotations

import re
import subprocess

from . import config
from .models import Collection, FetchError, GroundTruthEntry, Library
from .versions import GzVersion

#: Tags with a prefix we asked for and nothing else: this rejects the junk
#: (`gz-utils4_4.0.0-bcr-test`, `migrated_from_bitbucket`) and the pre-2020
#: `_pre1` spelling in one go.
_TAG_TAIL = r"(\d+\.\d+\.\d+(?:-pre\d+)?)$"


def repo_for(library: str) -> str:
    return config.GITHUB_REPO_OVERRIDES.get(library, library)


def repo_url(repo: str) -> str:
    return f"https://github.com/{config.GITHUB_ORG}/{repo}.git"


def candidate_tag_prefixes(library: str, major: int) -> tuple[str, ...]:
    """Tag prefixes a release of ``(library, major)`` may have used.

    gz-sim's tags say ``gazebo``, and everything released before Garden says
    ``ignition-``/``ign-``, so each lib gets several candidates instead of an
    era table: ``gz-sim`` 6 -> gz-sim6_, ignition-gazebo6_, ign-gazebo6_.

    The unsuffixed spellings come last because the very first ignition major
    predates the suffix convention (``ignition-tools_1.5.0`` is gz-tools 1).
    Picking the right major is left to the caller's major check, which is what
    keeps ``ignition-plugin_0.1.0`` out of gz-plugin 1's release list.
    """
    suffixed = [f"{library}{major}_"]
    unsuffixed = [f"{library}_"]
    if library.startswith("gz-"):
        stem = "gazebo" if library == "gz-sim" else library.removeprefix("gz-")
        suffixed += [f"ignition-{stem}{major}_", f"ign-{stem}{major}_"]
        unsuffixed += [f"ignition-{stem}_", f"ign-{stem}_"]
    return tuple(suffixed + unsuffixed)


def run_ls_remote(url: str) -> str:
    """Module level so the tests can monkeypatch the network away."""
    result = subprocess.run(
        ["git", "ls-remote", "--tags", url],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout


def parse_ls_remote(output: str) -> list[str]:
    """Tag names from ``git ls-remote`` output, minus the peeled ``^{}`` refs."""
    tags = []
    for line in output.splitlines():
        _, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/") or ref.endswith("^{}"):
            continue
        tags.append(ref[len("refs/tags/") :])
    return tags


def versions_for(tags: list[str], library: str, major: int) -> list[GzVersion]:
    """Every release of ``(library, major)`` found among ``tags``."""
    found: list[GzVersion] = []
    for prefix in candidate_tag_prefixes(library, major):
        pattern = re.compile(f"^{re.escape(prefix)}{_TAG_TAIL}")
        for tag in tags:
            match = pattern.match(tag)
            if not match:
                continue
            version = GzVersion.parse(match.group(1))
            # The tag must announce the major version it claims in its prefix.
            if version and version.major == major:
                found.append(version)
    return found


def entry_for(tags: list[str], library: Library) -> GroundTruthEntry:
    versions = versions_for(tags, library.name, library.major)
    stable = [v for v in versions if not v.is_prerelease]
    pre = [v for v in versions if v.is_prerelease]
    return GroundTruthEntry(
        library=library.name,
        major=library.major,
        latest_stable=str(max(stable)) if stable else None,
        latest_prerelease=str(max(pre)) if pre else None,
    )


def build_ground_truth(
    collections: list[Collection],
) -> tuple[list[GroundTruthEntry], list[FetchError]]:
    """One ``ls-remote`` per deduplicated repo, then one entry per (lib, major)."""
    libraries = sorted({lib for c in collections for lib in c.libraries})
    errors: list[FetchError] = []
    tags_by_repo: dict[str, list[str]] = {}
    for repo in sorted({repo_for(lib.name) for lib in libraries}):
        try:
            tags_by_repo[repo] = parse_ls_remote(run_ls_remote(repo_url(repo)))
        except (subprocess.SubprocessError, OSError) as exc:
            tags_by_repo[repo] = []
            errors.append(FetchError("ground_truth", f"{repo}: {exc}"))
    entries = [entry_for(tags_by_repo[repo_for(lib.name)], lib) for lib in libraries]
    return entries, errors

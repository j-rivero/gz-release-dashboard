"""Every URL, matrix and policy constant lives here, nowhere else."""

from __future__ import annotations

from . import __version__

USER_AGENT = f"gz-release-dashboard/{__version__} (+https://github.com/j-rivero/gz-release-dashboard)"
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3

# --- ground truth ---------------------------------------------------------
COLLECTIONS_YAML_URL = (
    "https://raw.githubusercontent.com/gazebo-tooling/release-tools/"
    "refs/heads/master/jenkins-scripts/dsl/gz-collections.yaml"
)
GITHUB_ORG = "gazebosim"
#: lib name -> GitHub repository, for the (currently none) cases where they differ.
GITHUB_REPO_OVERRIDES: dict[str, str] = {}

#: Collections never shown. EOL collections are simply deleted upstream.
IGNORED_COLLECTIONS = ("rotary",)
#: Belt-and-braces for the "no ci.configs means unreleased" heuristic.
IN_DEVELOPMENT_FALLBACK = ("m",)

# --- packages.osrfoundation.org -------------------------------------------
OSRF_DEB_BASE = "http://packages.osrfoundation.org/gazebo"
#: channel -> repository directory. The nightly repo is deliberately out of scope.
OSRF_DEB_CHANNELS = {"stable": "ubuntu-stable", "prerelease": "ubuntu-prerelease"}
#: Fallback only. The real list is derived per run from the packaging configs
#: in gz-collections.yaml, which is what keeps end-of-life releases such as
#: focal off the dashboard without anyone maintaining a list here.
OSRF_DEB_DISTROS = ("jammy", "noble", "resolute")
OSRF_DEB_ARCHES = ("amd64", "arm64", "armhf", "i386")

# --- conda-forge ----------------------------------------------------------
ANACONDA_PACKAGE_URL = "https://api.anaconda.org/package/conda-forge/{name}"
#: lib name -> conda-forge package name, when it is not simply the lib name.
CONDA_NAME_OVERRIDES: dict[str, str] = {}

# --- homebrew -------------------------------------------------------------
HOMEBREW_FORMULA_URL = (
    "https://raw.githubusercontent.com/osrf/homebrew-simulation/master/Formula/{formula}.rb"
)

# --- Bazel Central Registry ----------------------------------------------
#: The CDN, never the GitHub contents API: that one truncates at 1000 entries.
BCR_METADATA_URL = "https://bcr.bazel.build/modules/{module}/metadata.json"

# --- packages.ros.org -----------------------------------------------------
ROS_DEB_BASE = "http://packages.ros.org"
ROS_DEB_CHANNELS = {"ros2": "ros2", "ros2-testing": "ros2-testing"}
#: Fallback only; derived from gz-collections.yaml like OSRF_DEB_DISTROS.
ROS_DEB_DISTROS = ("noble", "resolute")
ROS_DEB_ARCHES = ("amd64", "arm64")

# --- status policy --------------------------------------------------------
#: Staging channels: they may carry a prerelease newer than the latest stable
#: tag, and whatever they are missing or holding stale is never a problem --
#: they contain only what happens to be queued at this instant.
PRERELEASE_CHANNELS = frozenset({"prerelease", "ros2-testing"})
#: Channels that overlay another channel of the same source instead of standing
#: on their own, as ``{source: {channel: the channel it sits on top of}}``.
#: The osrf prerelease repository is enabled alongside stable, so apt installs
#: whichever version is higher: a prerelease entry only means something while it
#: is ahead of stable. Anything at or below stable is the last release candidate
#: left behind after the release went out, and reporting it would be reporting
#: on history. ros2-testing is deliberately absent -- it is a full repository
#: that a sync drains into ros2, not an overlay, so being behind there is real.
OVERLAY_CHANNELS: dict[str, dict[str, str]] = {
    "osrf_debian": {"prerelease": "stable"},
}


def overlaid_channel(source: str, channel: str) -> str | None:
    """The channel ``channel`` sits on top of, or ``None`` if it stands alone."""
    return OVERLAY_CHANNELS.get(source, {}).get(channel)


#: ROS distributions that track the newest Gazebo instead of pinning to one
#: collection. Rolling is the only one, and it does not switch cleanly: it keeps
#: the previous generation's vendor packages around long after moving on, so it
#: carries two generations at once (jetty's and m's, as of writing). Matching on
#: (library, major) alone would therefore score jetty against a repository that
#: has already left it behind -- lyrical is jetty's ROS distribution now. Only
#: the newest collection Rolling really carries is scored against it.
ROLLING_ROSDISTROS = frozenset({"rolling"})
#: Libraries a source is known never to ship: absence is `—`, not `missing`.
EXPECTED_ABSENT: dict[str, frozenset[str]] = {
    "bazel_registry": frozenset({"gz-cmake", "gz-tools", "gz-gui", "gz-launch"}),
}

#: Fraction of a collection's libraries a platform must carry before the
#: dashboard holds that platform responsible for the rest. Majors are shared
#: between collections, so a single leaked package must not count as coverage.
COLLECTION_PLATFORM_SHARE = 0.5

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
#: Libraries a source is known never to ship: absence is `—`, not `missing`.
EXPECTED_ABSENT: dict[str, frozenset[str]] = {
    "bazel_registry": frozenset({"gz-cmake", "gz-tools", "gz-gui", "gz-launch"}),
}

#: Fraction of a collection's libraries a platform must carry before the
#: dashboard holds that platform responsible for the rest. Majors are shared
#: between collections, so a single leaked package must not count as coverage.
COLLECTION_PLATFORM_SHARE = 0.5

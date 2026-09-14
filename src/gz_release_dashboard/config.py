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
#: channel -> repository root. The nightly repo is deliberately out of scope.
OSRF_DEB_CHANNELS = {
    "stable": f"{OSRF_DEB_BASE}/ubuntu-stable",
    "prerelease": f"{OSRF_DEB_BASE}/ubuntu-prerelease",
}
#: Fallback only. The real list is derived per run from the packaging configs
#: in gz-collections.yaml, which is what keeps end-of-life releases such as
#: focal off the dashboard without anyone maintaining a list here.
OSRF_DEB_DISTROS = ("jammy", "noble", "resolute")
#: amd64 and arm64 are the whole of it. i386 is not supported by Gazebo, and
#: armhf production is being retired, so both are left unqueried: the packages
#: still sitting in the index for them are leftovers, and reading one as
#: evidence that an architecture is built is what turns a deliberate drop into
#: a reported gap.
OSRF_DEB_ARCHES = ("amd64", "arm64")


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

# --- packages.ros.org: the ROS 2 vendor packages --------------------------
ROS_DEB_BASE = "http://packages.ros.org"
#: channel -> repository root, as for the osrf repositories.
ROS_VENDOR_CHANNELS = {
    "ros2": f"{ROS_DEB_BASE}/ros2/ubuntu",
    "ros2-testing": f"{ROS_DEB_BASE}/ros2-testing/ubuntu",
}
#: Fallback only; derived from gz-collections.yaml like OSRF_DEB_DISTROS.
ROS_DEB_DISTROS = ("noble", "resolute")
ROS_DEB_ARCHES = ("amd64", "arm64")

# --- the ROS repositories that mirror the osrf packages -------------------
#: ROS does not only carry vendor packages: for the ignition era it mirrors the
#: gz source packages themselves, byte for byte the ones packages.osrfoundation
#: .org builds, which is what a ROS user on that generation actually installs.
#: ``ros_bootstrap`` is what the ROS buildfarm builds against and
#: ``ros2/ubuntu`` is what users apt-get, so a Gazebo release is only really
#: available to ROS once it has reached both.
ROS_GZ_DEB_CHANNELS = {
    "bootstrap": "http://repos.ros.org/repos/ros_bootstrap",
    "stable": f"{ROS_DEB_BASE}/ros2/ubuntu",
}

# --- dependencies ---------------------------------------------------------
#: The dependencies Gazebo packages or vendors itself, and how each build
#: system spells them. This is the one table in the dependency inventory that
#: is declared rather than derived: which collection uses which dependency, and
#: in which series, is read from each build's own declaration, but that
#: `libdart6.16-dev`, `dartsim-cpp` and `gz-dartsim-vendor` are one thing is
#: not written down anywhere upstream.
#:
#: Patterns are full-matched, so `libdart6.16-collision-bullet-dev` is not dart
#: itself. ROS patterns match a vendor's name after `ros-<rosdistro>-`; the
#: plain Debian names a ROS vendor depends on are matched with the `deb` ones.
#: A dependency only ever shows where a live build declares it, so an entry
#: nothing declares yet (mujoco) costs nothing.
DEPENDENCY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "ogre-next": {
        # ogre 2.x is ogre-next whatever its Debian package is called.
        "deb": (r"libogre-next(-\d+\.\d+)?-dev", r"libogre-2\.\d+-dev"),
        "brew": (r"ogre2\.\d+",),
        "conda": (r"ogre-next",),
        "bazel": (r"ogre-next",),
        "ros": (r"gz-ogre-next-vendor",),
    },
    "ogre": {
        "deb": (r"libogre-1\.\d+-dev",),
        "brew": (r"ogre1\.\d+",),
        "conda": (r"ogre",),
    },
    "dart": {
        "deb": (r"libdart(\d+\.\d+)?-dev",),
        "brew": (r"dartsim(@[\d.]+)?",),
        "conda": (r"dartsim-cpp", r"dartsim"),
        "bazel": (r"dartsim",),
        "ros": (r"gz-dartsim-vendor",),
    },
    "bullet": {
        "deb": (r"libbullet-dev",),
        "brew": (r"bullet(@[\d.]+)?",),
        "conda": (r"bullet-cpp", r"bullet"),
        "bazel": (r"bullet",),
    },
    "zenoh": {
        "deb": (r"libzenohc-dev", r"libzenohcpp-dev"),
        "conda": (r"libzenohc", r"zenoh-cpp"),
        "bazel": (r"zenoh-c", r"zenoh-cpp"),
        "ros": (r"zenoh-cpp-vendor",),
    },
    "mujoco": {
        "deb": (r"libmujoco(-[\d.]+)?-dev",),
        "brew": (r"mujoco",),
        "conda": (r"mujoco",),
        "bazel": (r"mujoco",),
        "ros": (r"mujoco-vendor",),
    },
}
#: Each dependency system follows one library source: it is fetched when that
#: source is, and applies to a collection when that source does, so a
#: collection never grows a dependency column its library table lacks.
DEPENDENCY_SYSTEMS: dict[str, str] = {
    "deb": "osrf_debian",
    "bazel": "bazel_registry",
    "conda": "conda_forge",
    "brew": "homebrew",
    "ros": "ros_vendor",
}
#: The channels a dependency system is read from, a column each, for the systems
#: read from more than one. ROS vendors are read from ros2 alone.
DEPENDENCY_CHANNELS: dict[str, tuple[str, ...]] = {
    "deb": ("stable", "prerelease"),
}
#: A packaging repository per (library, major), holding the debian/ tree the
#: osrf packages are built from.
GAZEBO_RELEASE_URL = "https://raw.githubusercontent.com/gazebo-release/{repo}/main/{path}"
#: The Ubuntu archive team's madison: every package, suite and architecture we
#: need in one small request, instead of a 19 MB universe index per
#: distribution and architecture.
MADISON_URL = "https://people.canonical.com/~ubuntu-archive/madison.cgi"
UBUNTU_POCKETS = ("", "-updates", "-security")
#: homebrew-core, for the dependencies the osrf/simulation tap does not carry.
HOMEBREW_CORE_FORMULA_URL = "https://formulae.brew.sh/api/formula/{formula}.json"
#: The MODULE.bazel of one registry version, pins included.
BCR_MODULE_URL = "https://bcr.bazel.build/modules/{module}/{version}/MODULE.bazel"


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

#: Sources that do not apply to a collection, as ``{collection: {sources}}``.
#: A source listed here is neither shown nor scored for that collection: no
#: column, no cells, no problems. Fortress predates every packaging system
#: that grew up around Gazebo later -- there is no Bazel module, no
#: conda-forge build and no ROS vendor package for the ignition generation --
#: so those three columns can only ever be empty for it, and an empty column
#: reads as a gap rather than as ground that was never claimed. The Bazel
#: Central Registry starts one generation later still: its oldest modules are
#: ionic's majors, and harmonic never had any.
COLLECTION_SOURCES_EXCLUDED: dict[str, frozenset[str]] = {
    "fortress": frozenset({"bazel_registry", "conda_forge", "ros_vendor"}),
    "harmonic": frozenset({"bazel_registry"}),
}
#: The reverse, as ``{source: {collections}}``: a source that applies to those
#: collections and to no other. The ROS repositories mirror the gz packages
#: only for the ignition generation; newer collections reach ROS as vendor
#: packages instead, which ``ros_vendor`` already reports.
COLLECTION_SOURCES_ONLY: dict[str, frozenset[str]] = {
    "ros_gz_debian": frozenset({"fortress"}),
}


def source_applies(source: str, collection: str) -> bool:
    """Whether ``source`` is meant to publish ``collection`` at all.

    The one gate for both halves of the question: the renderers ask it to
    decide whether to draw a column, and the status engine asks it to decide
    whether to score one. Asking it in one place is what keeps "not listed"
    and "not supported" the same fact.
    """
    if source in COLLECTION_SOURCES_EXCLUDED.get(collection, frozenset()):
        return False
    only = COLLECTION_SOURCES_ONLY.get(source)
    return only is None or collection in only


#: Fraction of a collection's libraries a platform must carry before the
#: dashboard holds that platform responsible for the rest. Majors are shared
#: between collections, so a single leaked package must not count as coverage.
COLLECTION_PLATFORM_SHARE = 0.5

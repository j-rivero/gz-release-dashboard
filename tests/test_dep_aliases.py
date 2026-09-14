import pytest

from gz_release_dashboard.deps.aliases import match_dependency


@pytest.mark.parametrize(
    "system,name,expected",
    [
        # The series lives in the Debian name, and osrf ships several at once.
        ("deb", "libdart6.16-dev", "dart"),
        ("deb", "libdart6.13-dev", "dart"),
        ("deb", "libdart-dev", "dart"),
        # Full match only: a component package is not the dependency itself.
        ("deb", "libdart6.16-collision-bullet-dev", None),
        ("deb", "libogre-next-2.3-dev", "ogre-next"),
        ("deb", "libogre-next-dev", "ogre-next"),
        # ogre 2.x is ogre-next whatever its package says; 1.x is plain ogre.
        ("deb", "libogre-2.2-dev", "ogre-next"),
        ("deb", "libogre-1.9-dev", "ogre"),
        ("deb", "libbullet-dev", "bullet"),
        ("deb", "libbullet3.24t64", None),
        ("deb", "libzenohc-dev", "zenoh"),
        ("deb", "libzenohcpp-dev", "zenoh"),
        ("deb", "libmujoco-3.5.0-dev", "mujoco"),
        ("deb", "libgz-math9-dev", None),
        ("brew", "ogre2.3", "ogre-next"),
        ("brew", "ogre1.9", "ogre"),
        ("brew", "dartsim", "dart"),
        ("brew", "dartsim@6.10.0", "dart"),
        ("brew", "bullet@2.87", "bullet"),
        ("brew", "gz-cmake4", None),
        # conda's `ogre` is ogre 1.x and must not swallow ogre-next.
        ("conda", "ogre", "ogre"),
        ("conda", "ogre-next", "ogre-next"),
        ("conda", "dartsim-cpp", "dart"),
        ("conda", "bullet-cpp", "bullet"),
        ("conda", "libzenohc", "zenoh"),
        ("bazel", "dartsim", "dart"),
        ("bazel", "zenoh-c", "zenoh"),
        ("bazel", "googletest", None),
        ("ros", "gz-ogre-next-vendor", "ogre-next"),
        ("ros", "gz-dartsim-vendor", "dart"),
        ("ros", "zenoh-cpp-vendor", "zenoh"),
        ("ros", "gz-sim-vendor", None),
        # A name is only ever read in its own system's spelling.
        ("conda", "libdart6.16-dev", None),
        ("bazel", "gz-dartsim-vendor", None),
    ],
)
def test_names_resolve_to_their_canonical_dependency(system, name, expected):
    assert match_dependency(system, name) == expected


def test_an_unknown_system_matches_nothing():
    assert match_dependency("pip", "dartsim") is None

import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.models import Collection, Library
from gz_release_dashboard.sources.debian_repo import packages_url
from gz_release_dashboard.sources.ros_vendor import RosVendorSource, parse_description


def url(channel, distro, arch):
    return packages_url(
        config.ROS_DEB_BASE, f"{config.ROS_DEB_CHANNELS[channel]}/ubuntu", distro, arch
    )


@pytest.fixture
def http():
    client = FakeHttpClient()
    client.add_gzip(url("ros2", "noble", "amd64"), fixture_text("ros-packages.txt"))
    return client


@pytest.fixture
def collections():
    return [
        Collection("harmonic", False, [Library("gz-sim", 8), Library("sdformat", 14)]),
        Collection("ionic", False, [Library("gz-sim", 9), Library("gz-fuel-tools", 9)]),
    ]


@pytest.fixture
def records(http, collections):
    return {(r.library, r.major): r for r in RosVendorSource(http).fetch(collections)}


def test_the_upstream_version_comes_from_the_description_not_the_version_field(records):
    sim = records[("gz-sim", 8)]
    assert sim.raw_version == "0.0.10-1noble.20260604.111001"
    assert sim.upstream_version == "8.11.0"


def test_an_underscored_upstream_name_is_canonicalised(records):
    # `gz-fuel_tools9` in the description, gz-fuel-tools everywhere else.
    assert ("gz-fuel-tools", 9) in records
    assert records[("gz-fuel-tools", 9)].upstream_version == "9.1.1"


def test_sdformat_has_no_gz_prefix(records):
    assert records[("sdformat", 14)].upstream_version == "14.9.0"


def test_vendors_with_a_different_description_grammar_are_skipped(records):
    # dartsim and ogre-next say "Vendor package for the ..." with no version pair.
    assert all("dart" not in library for library, _ in records)
    assert all("ogre" not in library for library, _ in records)


def test_debug_symbol_twins_are_ignored(records):
    assert all(not r.pkg_name.endswith("-dbgsym") for r in records.values())


def test_packages_that_are_not_vendors_are_ignored(records):
    assert all(r.pkg_name.endswith("-vendor") for r in records.values())


def test_the_rosdistro_rides_in_the_platform(records):
    assert records[("gz-sim", 8)].platform == "jazzy@noble"
    assert records[("gz-sim", 9)].platform == "rolling@noble"


def test_collection_membership_needs_no_rosdistro_table(http):
    # gz-sim 9 belongs to ionic; drop ionic and the rolling vendor disappears.
    records = RosVendorSource(http).fetch(
        [Collection("harmonic", False, [Library("gz-sim", 8)])]
    )
    assert {(r.library, r.major) for r in records} == {("gz-sim", 8)}


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Vendor package for: gz-sim8 8.11.0 Gazebo Sim", ("gz-sim", 8, "8.11.0")),
        ("Vendor package for: gz-fuel_tools9 9.1.1 x", ("gz-fuel-tools", 9, "9.1.1")),
        ("Vendor package for: sdformat14 14.9.0 x", ("sdformat", 14, "14.9.0")),
        ("Vendor package for: ignition-tools 1.5.0 x", ("gz-tools", 1, "1.5.0")),
        # lyrical and rolling drop the major from the name entirely.
        ("Vendor package for: gz-sim 10.5.0 x", ("gz-sim", 10, "10.5.0")),
        ("Vendor package for: gz-cmake 5.1.1 x", ("gz-cmake", 5, "5.1.1")),
        ("Vendor package for: gz-fuel_tools 11.0.0 x", ("gz-fuel-tools", 11, "11.0.0")),
        ("Vendor package for the DART physics engine v6.13.2", None),
        ("Vendor package for Ogre-next v2.3.3", None),
        ("Vendor package for: gz-sim8 9.0.0 mismatched major", None),
    ],
)
def test_parse_description(description, expected):
    assert parse_description(description) == expected


def test_channels_are_stable_and_pending_sync():
    assert RosVendorSource.channels == ("ros2", "ros2-testing")
    assert "ros2-testing" in config.PRERELEASE_CHANNELS


def test_an_unsuffixed_upstream_name_takes_its_major_from_the_version(http):
    """lyrical and rolling say `gz-sim 10.5.0`, not `gz-sim10 10.5.0`."""
    jetty = Collection(
        "jetty", False,
        [Library("gz-sim", 10), Library("gz-fuel-tools", 11), Library("gz-tools", 2)],
    )
    records = {(r.library, r.major): r for r in RosVendorSource(http).fetch([jetty])}
    assert records[("gz-sim", 10)].upstream_version == "10.5.0"
    assert records[("gz-sim", 10)].pkg_name == "ros-lyrical-gz-sim-vendor"
    assert records[("gz-fuel-tools", 11)].upstream_version == "11.0.0"
    # The suffixed spelling still works alongside it.
    assert records[("gz-tools", 2)].upstream_version == "2.0.3"


def test_an_unsuffixed_name_is_not_silently_treated_as_major_one():
    # The old fallback mapped `gz-sim 10.5.0` to major 1 and then dropped it.
    assert parse_description("Vendor package for: gz-sim 10.5.0 x") != ("gz-sim", 1, "10.5.0")

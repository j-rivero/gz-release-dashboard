"""The gz packages as ROS imports them: repos.ros.org and packages.ros.org.

Reading them is :class:`GzAptSource`'s job, the same code that reads
packages.osrfoundation.org, so what is worth asserting here is the wiring --
the two repositories, their channels, and that the ROS packages sharing the
index are not mistaken for Gazebo ones.
"""

import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.models import Collection, Library
from gz_release_dashboard.sources.debian_repo import packages_url
from gz_release_dashboard.sources.ros_gz_debian import RosGzDebianSource


def url(channel, distro, arch):
    return packages_url(config.ROS_GZ_DEB_CHANNELS[channel], distro, arch)


@pytest.fixture
def fortress():
    # The libraries the fixture index carries, without the gz-fortress
    # metapackage: upstream drops it from the collection and so do we.
    return [
        Collection(
            "fortress",
            False,
            [Library("gz-sim", 6), Library("gz-math", 6), Library("gz-common", 4)],
            ["jammy"],
        )
    ]


@pytest.fixture
def http():
    client = FakeHttpClient()
    client.add_gzip(url("bootstrap", "jammy", "amd64"),
                    fixture_text("ros-bootstrap-packages.txt"))
    return client


def records(http, collections):
    return RosGzDebianSource(http).fetch(collections)


def test_the_two_repositories_are_the_ones_ros_installs_from():
    assert config.ROS_GZ_DEB_CHANNELS["bootstrap"] == (
        "http://repos.ros.org/repos/ros_bootstrap"
    )
    assert config.ROS_GZ_DEB_CHANNELS["stable"] == (
        "http://packages.ros.org/ros2/ubuntu"
    )


def test_both_channels_are_queried_for_every_distro_and_arch(http, fortress):
    records(http, fortress)
    assert set(http.requested) == {
        url(channel, "jammy", arch)
        for channel in ("bootstrap", "stable")
        for arch in ("amd64", "arm64")
    }


def test_neither_channel_is_a_staging_one():
    """Both are repositories in their own right, so being behind is real."""
    assert not set(RosGzDebianSource.channels) & config.PRERELEASE_CHANNELS


def test_the_gz_source_packages_are_read_as_the_libraries_they_build(http, fortress):
    found = {(r.library, r.major): r for r in records(http, fortress)}
    assert set(found) == {("gz-sim", 6), ("gz-math", 6), ("gz-common", 4)}
    assert found[("gz-sim", 6)].pkg_name == "ignition-gazebo6"
    assert found[("gz-sim", 6)].platform == "jammy"
    assert found[("gz-sim", 6)].channel == "bootstrap"


def test_an_import_that_lags_behind_reports_the_version_it_holds(http, fortress):
    found = {r.library: r.upstream_version for r in records(http, fortress)}
    # What packages.osrfoundation.org shipped is 4.9.0 and 6.17.0; the import
    # is a release behind on both, which is the whole point of the columns.
    assert found["gz-common"] == "4.8.1"
    assert found["gz-math"] == "6.16.0"


def test_a_republished_binary_counts_as_its_newest_stanza(http, fortress):
    """The index still carries libignition-gazebo6 6.16.0 next to 6.18.0."""
    found = {r.library: r.upstream_version for r in records(http, fortress)}
    assert found["gz-sim"] == "6.18.0"


def test_the_ros_packages_sharing_the_index_are_not_gazebo_ones(http, fortress):
    """python3-bloom lives in the same repository and is nobody's library."""
    assert not [r for r in records(http, fortress) if "bloom" in r.pkg_name]


def test_the_collection_metapackage_is_left_out(http, fortress):
    """ignition-fortress is the collection, not a library in it."""
    assert not [r for r in records(http, fortress) if r.library == "gz-fortress"]


def test_only_fortress_is_asked_for():
    """The import exists for the ignition generation and nothing newer."""
    assert config.source_applies("ros_gz_debian", "fortress")
    assert not config.source_applies("ros_gz_debian", "jetty")
